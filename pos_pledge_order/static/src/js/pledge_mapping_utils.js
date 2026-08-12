/** @odoo-module */

/**
 * Site Service menu product → pledge product mapping helpers.
 * Pledge is determined ONLY by pledge_product_id on site service menu lines.
 */

function normalizeProductId(value) {
    if (!value) {
        return null;
    }
    if (typeof value === "number") {
        return value;
    }
    if (Array.isArray(value)) {
        return value[0] || null;
    }
    if (typeof value === "object" && value.id) {
        return value.id;
    }
    return null;
}

export function getMenuPledgeMap(pos) {
    const map = new Map();
    const lines = pos?.models?.["pos.site.service.product.line"]?.getAll?.() || [];
    for (const line of lines) {
        const menuProductId = normalizeProductId(line.product_id);
        const pledgeProductId = normalizeProductId(line.pledge_product_id);
        if (menuProductId && pledgeProductId) {
            map.set(menuProductId, pledgeProductId);
        }
    }
    return map;
}

export function getPledgeProductForMenuProduct(pos, menuProduct) {
    const menuProductId = normalizeProductId(menuProduct);
    if (!menuProductId) {
        return null;
    }
    const pledgeProductId = getMenuPledgeMap(pos).get(menuProductId);
    if (!pledgeProductId) {
        return null;
    }
    return pos.models["product.product"].get(pledgeProductId) || null;
}

export function menuProductHasPledgeMapping(pos, menuProduct) {
    const menuProductId = normalizeProductId(menuProduct);
    return menuProductId ? getMenuPledgeMap(pos).has(menuProductId) : false;
}

export function resolvePledgeUnitAmount(pledgeProduct) {
    if (!pledgeProduct) {
        return 0;
    }
    const configured = Number(pledgeProduct.pledge_amount || 0);
    if (configured > 0) {
        return configured;
    }
    return Number(pledgeProduct.lst_price || 0);
}

export function getLineProduct(line) {
    return (
        (line.get_product && line.get_product()) ||
        (line.getProduct && line.getProduct()) ||
        line.product ||
        line.product_id
    );
}

export function orderHasMappedPledgeProducts(order, pos) {
    if (!order) {
        return false;
    }
    const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
    return lines.some((line) => menuProductHasPledgeMapping(pos, getLineProduct(line)));
}

export function computeMappedPledgeDetails(order, pos) {
    const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
    const pledgeDetails = [];
    let totalPledgeAmount = 0;
    const pledgeProductIds = [];

    for (const line of lines) {
        const menuProduct = getLineProduct(line);
        const pledgeProduct = getPledgeProductForMenuProduct(pos, menuProduct);
        if (!pledgeProduct) {
            continue;
        }
        const qty = line.get_quantity ? line.get_quantity() : line.qty || 0;
        const unitPledge = resolvePledgeUnitAmount(pledgeProduct);
        const lineTotal = unitPledge * qty;
        if (lineTotal <= 0) {
            continue;
        }
        totalPledgeAmount += lineTotal;
        pledgeProductIds.push(pledgeProduct.id);
        pledgeDetails.push({
            menu_product_name: menuProduct.display_name || menuProduct.name,
            product_name: pledgeProduct.display_name || pledgeProduct.name,
            pledge_amount: unitPledge,
            quantity: qty,
            total: lineTotal,
            pledge_product_id: pledgeProduct.id,
            menu_product_id: menuProduct.id,
        });
    }

    return {
        totalPledgeAmount,
        pledgeDetails,
        pledgeProductIds: [...new Set(pledgeProductIds)],
        hasPledge: pledgeDetails.length > 0,
    };
}

export function lineHasPledgeMapping(pos, line) {
    return menuProductHasPledgeMapping(pos, getLineProduct(line));
}
