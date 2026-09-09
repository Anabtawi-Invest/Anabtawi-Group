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

/** Prefer product.pledge_amount; fall back to lst_price (same as advance order product line). */
function resolveConfiguredPledgeAmount(pledgeProduct) {
    if (!pledgeProduct) {
        return 0;
    }
    const configured = Number(pledgeProduct.pledge_amount || 0);
    if (configured > 0) {
        return configured;
    }
    return Number(pledgeProduct.lst_price || 0);
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
    map = await fetchMenuPledgeMapFromServer(orm);
    return map;
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
 * price_unit = pledge_amount if set, else lst_price
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
        let pledgeProduct = pos.models?.["product.product"]?.get(pledgeProductId);
        if (!pledgeProduct) {
            // Product may not be in the local POS cache; try loading by id via models.
            pledgeProduct = pos.models?.["product.product"]?.getAll?.()?.find(
                (p) => normalizeProductId(p) === pledgeProductId
            );
        }
        const unitAmount = resolveConfiguredPledgeAmount(pledgeProduct);
        if (!unitAmount) {
            skippedNoAmount.push(pledgeProductId);
            continue;
        }
        const qty = Number(line.get_quantity?.() ?? line.getQuantity?.() ?? line.qty ?? 0);
        if (qty <= 0) {
            continue;
        }
        const prev = qtyByPledgeId.get(pledgeProductId) || {
            qty: 0,
            unitAmount,
            pledgeProduct,
        };
        prev.qty += qty;
        prev.unitAmount = unitAmount;
        prev.pledgeProduct = pledgeProduct || prev.pledgeProduct;
        qtyByPledgeId.set(pledgeProductId, prev);
    }

    if (!qtyByPledgeId.size) {
        console.warn("[ONSITE_PLEDGE] Mapping found but no pledge lines to add.", {
            mapSize: menuToPledge.size,
            skippedNoAmount,
        });
        return {
            added: false,
            lineCount: 0,
            skippedNoAmount,
            noMatchingCartProducts: skippedNoAmount.length === 0,
        };
    }

    const existingProductIds = new Set(
        (order.getOrderlines?.() || order.lines || [])
            .map((line) => normalizeProductId(getLineProduct(line)))
            .filter(Boolean)
    );

    let addedCount = 0;
    const missingProducts = [];
    for (const [pledgeProductId, info] of qtyByPledgeId.entries()) {
        if (existingProductIds.has(pledgeProductId)) {
            continue;
        }
        const pledgeProduct = info.pledgeProduct;
        if (!pledgeProduct?.product_tmpl_id) {
            missingProducts.push(pledgeProductId);
            console.warn("[ONSITE_PLEDGE] Pledge product not loaded in POS:", pledgeProductId);
            continue;
        }
        const newLine = await pos.addLineToCurrentOrder(
            {
                product_tmpl_id: pledgeProduct.product_tmpl_id,
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
