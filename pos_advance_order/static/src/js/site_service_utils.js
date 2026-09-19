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
    const cuttingServiceProductId = normalizeId(menu.cutting_service_product_id);
    if (!serviceProductId && !cuttingServiceProductId) {
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
        cuttingServiceProductId,
        servicePrice: menu.service_price ?? 0,
        serviceProductName: "",
        cuttingServiceProductName: "",
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
            [
                "id",
                "enable_site_service",
                "threshold",
                "service_product_id",
                "cutting_service_product_id",
                "service_price",
            ],
            { limit: 1 }
        );
        if (!menus.length) {
            return null;
        }
        const menu = menus[0];
        const serviceProductId = normalizeId(menu.service_product_id);
        const cuttingServiceProductId = normalizeId(menu.cutting_service_product_id);
        if (!serviceProductId && !cuttingServiceProductId) {
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
            cuttingServiceProductId,
            servicePrice: menu.service_price ?? 0,
            serviceProductName: Array.isArray(menu.service_product_id)
                ? menu.service_product_id[1]
                : "",
            cuttingServiceProductName: Array.isArray(menu.cutting_service_product_id)
                ? menu.cutting_service_product_id[1]
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

/** Product id → multiple factor from the Site Service configuration. */
export function getSiteServiceMultiplesMap(menuConfig) {
    const multiplesByProduct = new Map();
    for (const line of menuConfig?.productLines || []) {
        const productId = normalizeId(line.product_id);
        if (productId) {
            multiplesByProduct.set(productId, line.multiple || 0);
        }
    }
    return multiplesByProduct;
}

/** True when the order contains at least one non-service product listed in Site Service. */
export function hasListedSiteServiceProducts(lines, menuConfig) {
    const multiplesByProduct = getSiteServiceMultiplesMap(menuConfig);
    if (!multiplesByProduct.size) {
        return false;
    }
    for (const line of lines || []) {
        if (line.is_site_service_auto) {
            continue;
        }
        const productId = normalizeId(line.product_id);
        if (productId && multiplesByProduct.has(productId)) {
            return true;
        }
    }
    return false;
}

export function computeSiteServiceScoreFromLines(lines, menuConfig) {
    const multiplesByProduct = getSiteServiceMultiplesMap(menuConfig);
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

/**
 * Resolve which product + unit price to use for an auto service line.
 * options: { serviceType, unitPrice, productId }
 */
export function resolveServiceLineTarget(menuConfig, options = {}) {
    const serviceType = options.serviceType || "on_site";
    if (serviceType === "cutting") {
        const productId = options.productId || menuConfig?.cuttingServiceProductId;
        const unitPrice =
            options.unitPrice !== undefined && options.unitPrice !== null
                ? Number(options.unitPrice)
                : 0;
        return { serviceType, productId, unitPrice };
    }
    if (serviceType === "on_site") {
        const productId = options.productId || menuConfig?.serviceProductId;
        const unitPrice =
            options.unitPrice !== undefined && options.unitPrice !== null
                ? Number(options.unitPrice)
                : Number(menuConfig?.servicePrice || 0);
        return { serviceType, productId, unitPrice };
    }
    return { serviceType: "none", productId: null, unitPrice: 0 };
}

export function appendSiteServiceLineIfNeeded(lines, pos, menuConfig = null, options = {}) {
    const config = menuConfig || getSiteServiceConfig(pos);
    if (!config) {
        return { lines: lines || [], added: false, score: 0, menuConfig: null };
    }
    const serviceType = options.serviceType || "on_site";
    if (serviceType === "none") {
        const productLines = (lines || []).filter((line) => !line.is_site_service_auto);
        return { lines: productLines, added: false, score: 0, menuConfig: config };
    }
    const productLines = (lines || []).filter((line) => !line.is_site_service_auto);
    // Price comes from the matching On-Site Prices range (qty × multiple + popup choice).
    // No threshold: always add when Site Service or Cutting is selected.
    const score = computeSiteServiceScoreFromLines(productLines, config);
    const target = resolveServiceLineTarget(config, { ...options, serviceType });
    if (!target.productId) {
        return { lines: productLines, added: false, score, menuConfig: config, missingProduct: true };
    }
    const serviceProduct = pos.models?.["product.product"]?.get(target.productId);
    const serviceProductName =
        serviceProduct?.display_name ||
        serviceProduct?.name ||
        (serviceType === "cutting"
            ? config.cuttingServiceProductName
            : config.serviceProductName) ||
        "";
    if (!serviceProduct && !serviceProductName) {
        return { lines: productLines, added: false, score, menuConfig: config, missingProduct: true };
    }
    if (productLines.some((line) => normalizeId(line.product_id) === target.productId)) {
        return { lines: productLines, added: false, score, menuConfig: config };
    }
    return {
        lines: [
            ...productLines,
            {
                product_id: target.productId,
                product_name: serviceProductName,
                qty: 1,
                price_unit: target.unitPrice,
                is_site_service_auto: true,
            },
        ],
        added: true,
        score,
        menuConfig: config,
        serviceType,
    };
}

export function prepareLinesFromPosOrder(order) {
    return (order?.getOrderlines?.() || order?.lines || [])
        .filter((line) => !line.is_site_service_auto)
        .map((line) => {
            const product = line.getProduct?.() || line.product || line.product_id;
            const productId = normalizeId(product?.id ?? product);
            const qty = Number(line.getQuantity?.() ?? line.qty ?? 0);
            return { product_id: productId, qty };
        })
        .filter((line) => line.product_id && line.qty > 0);
}

export function removeAutoSiteServiceLines(order) {
    if (!order) {
        return;
    }
    const lines = [...(order.getOrderlines?.() || order.lines || [])];
    for (const line of lines) {
        if (line.is_site_service_auto) {
            order.removeOrderline(line);
        }
    }
}

/**
 * Add or remove the service/cutting line on a live POS cart.
 * Third argument may be a boolean (legacy isOnSite) or options:
 *   { serviceType, unitPrice, productId, menuConfig }
 */
export async function applySiteServiceToPosOrder(pos, order, isOnSiteOrOptions, menuConfig = null) {
    removeAutoSiteServiceLines(order);
    let options = {};
    if (typeof isOnSiteOrOptions === "boolean") {
        options = { serviceType: isOnSiteOrOptions ? "on_site" : "none" };
    } else if (isOnSiteOrOptions && typeof isOnSiteOrOptions === "object") {
        options = { ...isOnSiteOrOptions };
    } else {
        options = { serviceType: "none" };
    }
    const serviceType = options.serviceType || "none";
    if (serviceType === "none" || !order) {
        return { added: false, score: 0, serviceType };
    }
    let config = options.menuConfig || menuConfig || getSiteServiceConfig(pos);
    if (!config) {
        const orm = pos?.data?.orm || pos?.env?.services?.orm;
        config = await resolveSiteServiceConfig(pos, orm);
    }
    if (!config) {
        console.warn("[SITE_SERVICE] Payment: no site service configuration loaded.");
        return { added: false, score: 0, missingConfig: true, serviceType };
    }
    const plainLines = prepareLinesFromPosOrder(order);
    const result = appendSiteServiceLineIfNeeded(plainLines, pos, config, options);
    if (!result.added) {
        if (result.menuConfig) {
            console.info(
                `[SITE_SERVICE] Payment: service not added (type=${serviceType}, score=${result.score}, skipped=${Boolean(result.skipped)}).`
            );
        }
        return { ...result, serviceType };
    }
    const target = resolveServiceLineTarget(config, options);
    const serviceProduct = pos.models?.["product.product"]?.get(target.productId);
    if (!serviceProduct?.product_tmpl_id) {
        console.warn("[SITE_SERVICE] Payment: service product not loaded in POS.", target.productId);
        return { ...result, added: false, missingProduct: true, serviceType };
    }
    const newLine = await pos.addLineToCurrentOrder(
        {
            product_tmpl_id: serviceProduct.product_tmpl_id,
            qty: 1,
            price_unit: target.unitPrice,
            is_site_service_auto: true,
        },
        {},
        false
    );
    if (newLine) {
        newLine.is_site_service_auto = true;
        if (typeof newLine.setUnitPrice === "function") {
            newLine.price_type = "manual";
            newLine.setUnitPrice(target.unitPrice);
        } else {
            newLine.price_unit = target.unitPrice;
        }
    }
    console.info(
        `[SITE_SERVICE] Payment: added ${serviceType} line (score=${result.score}, price=${target.unitPrice}).`
    );
    return { ...result, added: Boolean(newLine), serviceType };
}
