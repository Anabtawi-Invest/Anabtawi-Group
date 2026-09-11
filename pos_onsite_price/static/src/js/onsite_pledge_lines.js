/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import {
    getLineProduct,
    getMenuPledgeMap,
    normalizeProductId,
} from "@pos_pledge_order/js/pledge_mapping_utils";

patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.is_onsite_auto_pledge_line = vals?.is_onsite_auto_pledge_line || false;
    },
});

/** Prefer product.pledge_amount; fall back to sales price fields used in POS. */
function resolveConfiguredPledgeAmount(pledgeProduct) {
    if (!pledgeProduct) {
        return 0;
    }
    const configured = Number(pledgeProduct.pledge_amount || 0);
    if (configured > 0) {
        return configured;
    }
    const salesPrice = Number(
        pledgeProduct.lst_price ||
            pledgeProduct.list_price ||
            pledgeProduct.product_tmpl_id?.list_price ||
            pledgeProduct.product_tmpl_id?.lst_price ||
            0
    );
    return salesPrice > 0 ? salesPrice : 0;
}

function normalizeId(value) {
    return normalizeProductId(value);
}

async function fetchMenuPledgeMapFromServer(orm) {
    const map = new Map();
    if (!orm) {
        return map;
    }
    try {
        const lines = await orm.searchRead(
            "pos.site.service.product.line",
            [
                ["menu_id.active", "=", true],
                ["menu_id.enable_site_service", "=", true],
                ["pledge_product_id", "!=", false],
            ],
            ["product_id", "pledge_product_id"]
        );
        for (const line of lines || []) {
            const menuProductId = normalizeId(line.product_id);
            const pledgeProductId = normalizeId(line.pledge_product_id);
            if (menuProductId && pledgeProductId) {
                map.set(menuProductId, pledgeProductId);
            }
        }
    } catch (error) {
        console.warn("[ONSITE_PLEDGE] Failed to fetch site service pledge map", error);
    }
    return map;
}

async function resolveMenuPledgeMap(pos) {
    let map = getMenuPledgeMap(pos);
    if (map.size) {
        return map;
    }
    const orm = pos?.data?.orm || pos?.env?.services?.orm;
    return await fetchMenuPledgeMapFromServer(orm);
}

async function ensurePledgeProductLoaded(pos, pledgeProductId) {
    let pledgeProduct = pos.models?.["product.product"]?.get(pledgeProductId);
    if (pledgeProduct?.product_tmpl_id) {
        return pledgeProduct;
    }
    try {
        if (pos.data?.read) {
            const records = await pos.data.read("product.product", [pledgeProductId]);
            pledgeProduct =
                (Array.isArray(records) ? records[0] : null) ||
                pos.models?.["product.product"]?.get(pledgeProductId);
        }
        if (!pledgeProduct && pos.data?.searchRead) {
            await pos.data.searchRead("product.product", [["id", "=", pledgeProductId]]);
            pledgeProduct = pos.models?.["product.product"]?.get(pledgeProductId);
        }
        if (!pledgeProduct) {
            const orm = pos?.data?.orm || pos?.env?.services?.orm;
            if (orm) {
                const rows = await orm.searchRead(
                    "product.product",
                    [["id", "=", pledgeProductId]],
                    ["id", "lst_price", "list_price", "pledge_amount", "display_name", "product_tmpl_id"]
                );
                if (rows?.length) {
                    // Soft fallback object when product is not connectable into POS models.
                    return {
                        id: rows[0].id,
                        lst_price: rows[0].lst_price,
                        list_price: rows[0].list_price,
                        pledge_amount: rows[0].pledge_amount,
                        display_name: rows[0].display_name,
                        product_tmpl_id: Array.isArray(rows[0].product_tmpl_id)
                            ? { id: rows[0].product_tmpl_id[0] }
                            : rows[0].product_tmpl_id,
                        _fromServerFallback: true,
                    };
                }
            }
        }
    } catch (error) {
        console.warn("[ONSITE_PLEDGE] Failed to load pledge product", pledgeProductId, error);
    }
    return pledgeProduct || null;
}

export function removeAutoOnsitePledgeLines(order) {
    if (!order) {
        return;
    }
    const lines = [...(order.getOrderlines?.() || order.lines || [])];
    for (const line of lines) {
        if (line.is_onsite_auto_pledge_line) {
            order.removeOrderline(line);
        }
    }
}

/**
 * Normal POS payment (no advance):
 * - On-site Yes  → never add pledge lines (remove auto ones).
 * - On-site No   → add mapped pledge product lines.
 *
 * price_unit = pledge_amount if set, else sales price (lst_price)
 * qty        = sum of mapped menu product quantities
 */
export async function applyOnsitePledgeLinesToPosOrder(pos, order, isOnSite) {
    removeAutoOnsitePledgeLines(order);
    if (isOnSite || !order) {
        return { added: false, lineCount: 0, skippedOnSite: Boolean(isOnSite) };
    }

    const menuToPledge = await resolveMenuPledgeMap(pos);
    if (!menuToPledge.size) {
        console.warn("[ONSITE_PLEDGE] No site-service pledge mapping loaded.");
        return { added: false, lineCount: 0, missingMapping: true };
    }

    const qtyByPledgeId = new Map();
    const skippedNoAmount = [];
    const missingProducts = [];
    const lines = order.getOrderlines?.() || order.lines || [];

    for (const line of lines) {
        if (line.is_onsite_auto_pledge_line || line.is_site_service_auto) {
            continue;
        }
        const menuProduct = getLineProduct(line);
        const menuProductId = normalizeProductId(menuProduct);
        if (!menuProductId) {
            continue;
        }
        const pledgeProductId = menuToPledge.get(menuProductId);
        if (!pledgeProductId) {
            continue;
        }

        const qty = Number(line.get_quantity?.() ?? line.getQuantity?.() ?? line.qty ?? 0);
        if (qty <= 0) {
            continue;
        }

        const prev = qtyByPledgeId.get(pledgeProductId) || {
            qty: 0,
            unitAmount: 0,
            pledgeProduct: null,
        };
        prev.qty += qty;
        qtyByPledgeId.set(pledgeProductId, prev);
    }

    // Resolve products / prices after aggregating quantities.
    for (const [pledgeProductId, info] of qtyByPledgeId.entries()) {
        const pledgeProduct = await ensurePledgeProductLoaded(pos, pledgeProductId);
        if (!pledgeProduct) {
            missingProducts.push(pledgeProductId);
            continue;
        }
        const unitAmount = resolveConfiguredPledgeAmount(pledgeProduct);
        if (!unitAmount) {
            skippedNoAmount.push(pledgeProductId);
            continue;
        }
        info.pledgeProduct = pledgeProduct;
        info.unitAmount = unitAmount;
    }

    // Drop entries that could not be priced / loaded.
    for (const pledgeProductId of [...qtyByPledgeId.keys()]) {
        const info = qtyByPledgeId.get(pledgeProductId);
        if (!info?.pledgeProduct || !info.unitAmount) {
            qtyByPledgeId.delete(pledgeProductId);
        }
    }

    if (!qtyByPledgeId.size) {
        console.warn("[ONSITE_PLEDGE] Nothing to add after resolving products.", {
            mapSize: menuToPledge.size,
            missingProducts,
            skippedNoAmount,
        });
        return {
            added: false,
            lineCount: 0,
            missingProducts,
            skippedNoAmount,
        };
    }

    const existingProductIds = new Set(
        (order.getOrderlines?.() || order.lines || [])
            .map((line) => normalizeProductId(getLineProduct(line)))
            .filter(Boolean)
    );

    let addedCount = 0;
    for (const [pledgeProductId, info] of qtyByPledgeId.entries()) {
        if (existingProductIds.has(pledgeProductId)) {
            continue;
        }
        const pledgeProduct = info.pledgeProduct;
        const template =
            pledgeProduct.product_tmpl_id ||
            (pledgeProduct.product_tmpl_id?.id
                ? pledgeProduct.product_tmpl_id
                : null);
        if (!template) {
            missingProducts.push(pledgeProductId);
            console.warn("[ONSITE_PLEDGE] Pledge product has no template:", pledgeProductId);
            continue;
        }
        const newLine = await pos.addLineToCurrentOrder(
            {
                product_tmpl_id: template,
                qty: info.qty,
                price_unit: info.unitAmount,
                price_type: "manual",
                is_onsite_auto_pledge_line: true,
            },
            {},
            false
        );
        if (newLine) {
            newLine.is_onsite_auto_pledge_line = true;
            if (typeof newLine.setUnitPrice === "function") {
                newLine.price_type = "manual";
                newLine.setUnitPrice(info.unitAmount);
            } else {
                newLine.price_unit = info.unitAmount;
            }
            addedCount += 1;
            existingProductIds.add(pledgeProductId);
            console.info("[ONSITE_PLEDGE] Added pledge line", {
                pledgeProductId,
                qty: info.qty,
                unitAmount: info.unitAmount,
            });
        } else {
            missingProducts.push(pledgeProductId);
            console.warn("[ONSITE_PLEDGE] addLineToCurrentOrder returned null", pledgeProductId);
        }
    }

    return {
        added: addedCount > 0,
        lineCount: addedCount,
        missingProducts,
        skippedNoAmount,
    };
}
