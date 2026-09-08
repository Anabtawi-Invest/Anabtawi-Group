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

function resolveConfiguredPledgeAmount(pledgeProduct) {
    const amount = Number(pledgeProduct?.pledge_amount || 0);
    return amount > 0 ? amount : 0;
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
 * - On-site No   → add mapped pledge product lines when pledge_amount is set.
 *
 * price_unit = product.pledge_amount only (no lst_price fallback).
 * qty        = sum of mapped menu product quantities.
 */
export async function applyOnsitePledgeLinesToPosOrder(pos, order, isOnSite) {
    removeAutoOnsitePledgeLines(order);
    if (isOnSite || !order) {
        return { added: false, lineCount: 0, skippedOnSite: Boolean(isOnSite) };
    }

    const menuToPledge = getMenuPledgeMap(pos);
    if (!menuToPledge.size) {
        return { added: false, lineCount: 0, missingMapping: true };
    }

    const qtyByPledgeId = new Map();
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
        const pledgeProduct = pos.models?.["product.product"]?.get(pledgeProductId);
        const unitAmount = resolveConfiguredPledgeAmount(pledgeProduct);
        if (!unitAmount) {
            continue;
        }
        const qty = Number(line.get_quantity?.() ?? line.getQuantity?.() ?? line.qty ?? 0);
        if (qty <= 0) {
            continue;
        }
        const prev = qtyByPledgeId.get(pledgeProductId) || { qty: 0, unitAmount, pledgeProduct };
        prev.qty += qty;
        qtyByPledgeId.set(pledgeProductId, prev);
    }

    if (!qtyByPledgeId.size) {
        return { added: false, lineCount: 0 };
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
                newLine.setUnitPrice(info.unitAmount);
            } else {
                newLine.price_unit = info.unitAmount;
            }
            addedCount += 1;
            existingProductIds.add(pledgeProductId);
        }
    }

    return {
        added: addedCount > 0,
        lineCount: addedCount,
        missingProducts,
    };
}
