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
        serviceProductName: "",
        productLines,
    };
}

/** Load site service from backend when POS data models are not loaded yet. */
export async function fetchSiteServiceConfigFromServer(orm) {
    try {
        const menus = await orm.searchRead(
            "pos.site.service.menu",
            [
                ["active", "=", true],
                ["enable_site_service", "=", true],
            ],
            ["id", "enable_site_service", "threshold", "service_product_id", "service_price"],
            { limit: 1 }
        );
        if (!menus.length) {
            return null;
        }
        const menu = menus[0];
        const serviceProductId = normalizeId(menu.service_product_id);
        if (!serviceProductId) {
            return null;
        }
        const productLines = await orm.searchRead(
            "pos.site.service.product.line",
            [["menu_id", "=", menu.id]],
            ["product_id", "multiple"]
        );
        return {
            threshold: menu.threshold ?? 31,
            serviceProductId,
            servicePrice: menu.service_price ?? 0,
            serviceProductName: Array.isArray(menu.service_product_id)
                ? menu.service_product_id[1]
                : "",
            productLines: productLines.map((line) => ({
                product_id: line.product_id,
                multiple: line.multiple,
            })),
        };
    } catch {
        return null;
    }
}

export async function resolveSiteServiceConfig(pos, orm) {
    return getSiteServiceConfig(pos) || (orm ? await fetchSiteServiceConfigFromServer(orm) : null);
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

export function appendSiteServiceLineIfNeeded(lines, pos, menuConfig = null) {
    const config = menuConfig || getSiteServiceConfig(pos);
    if (!config) {
        return { lines: lines || [], added: false, score: 0, menuConfig: null };
    }
    const productLines = (lines || []).filter((line) => !line.is_site_service_auto);
    const score = computeSiteServiceScoreFromLines(productLines, config);
    if (score >= config.threshold) {
        return { lines: productLines, added: false, score, menuConfig: config };
    }
    const serviceProduct = pos.models?.["product.product"]?.get(config.serviceProductId);
    const serviceProductName =
        serviceProduct?.display_name ||
        serviceProduct?.name ||
        config.serviceProductName ||
        "";
    if (!serviceProduct && !serviceProductName) {
        return { lines: productLines, added: false, score, menuConfig: config, missingProduct: true };
    }
    if (productLines.some((line) => normalizeId(line.product_id) === config.serviceProductId)) {
        return { lines: productLines, added: false, score, menuConfig: config };
    }
    return {
        lines: [
            ...productLines,
            {
                product_id: config.serviceProductId,
                product_name: serviceProductName,
                qty: 1,
                price_unit: config.servicePrice,
                is_site_service_auto: true,
            },
        ],
        added: true,
        score,
        menuConfig: config,
    };
}
