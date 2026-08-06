/** @odoo-module */

export function normalizeId(value) {
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

export function getSiteServiceConfig(pos) {
    const config = pos?.config;
    if (!config) {
        return null;
    }
    const menuModel = pos.models?.["pos.site.service.menu"];
    if (!menuModel) {
        return null;
    }
    const menus = menuModel.getAll?.() || [];
    const menu = menus.find((record) => record.enable_site_service) || menus[0];
    if (!menu || !menu.enable_site_service) {
        return null;
    }
    const serviceProductId = normalizeId(menu.service_product_id);
    if (!serviceProductId) {
        return null;
    }
    const lineModel = pos.models?.["pos.site.service.product.line"];
    const menuId = normalizeId(menu.id);
    const productLines = (lineModel?.getAll?.() || []).filter(
        (line) => normalizeId(line.menu_id) === menuId
    );
    return {
        threshold: menu.threshold ?? 31,
        serviceProductId,
        servicePrice: menu.service_price ?? 0,
        productLines,
    };
}

export function computeSiteServiceScoreFromLines(lines, menuConfig) {
    const multiplesByProduct = new Map();
    for (const line of menuConfig.productLines) {
        const productId = normalizeId(line.product_id);
        if (productId) {
            multiplesByProduct.set(productId, line.multiple || 0);
        }
    }
    let score = 0;
    for (const line of lines || []) {
        if (line.is_site_service_auto) {
            continue;
        }
        const productId = normalizeId(line.product_id);
        if (!productId || !multiplesByProduct.has(productId)) {
            continue;
        }
        const qty = Number(line.qty) || 0;
        score += qty * multiplesByProduct.get(productId);
    }
    return score;
}

export function appendSiteServiceLineIfNeeded(lines, pos) {
    const menuConfig = getSiteServiceConfig(pos);
    if (!menuConfig) {
        return { lines: lines || [], added: false, score: 0, menuConfig: null };
    }
    const productLines = (lines || []).filter((line) => !line.is_site_service_auto);
    const score = computeSiteServiceScoreFromLines(productLines, menuConfig);
    if (score >= menuConfig.threshold) {
        return { lines: productLines, added: false, score, menuConfig };
    }
    const serviceProduct = pos.models["product.product"].get(menuConfig.serviceProductId);
    if (!serviceProduct) {
        return { lines: productLines, added: false, score, menuConfig, missingProduct: true };
    }
    if (productLines.some((line) => normalizeId(line.product_id) === menuConfig.serviceProductId)) {
        return { lines: productLines, added: false, score, menuConfig };
    }
    return {
        lines: [
            ...productLines,
            {
                product_id: menuConfig.serviceProductId,
                product_name: serviceProduct.display_name || serviceProduct.name || "",
                qty: 1,
                price_unit: menuConfig.servicePrice,
                is_site_service_auto: true,
            },
        ],
        added: true,
        score,
        menuConfig,
    };
}
