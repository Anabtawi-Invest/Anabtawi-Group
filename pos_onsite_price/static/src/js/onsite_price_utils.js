/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { OnSitePricePopup } from "@pos_onsite_price/js/onsite_price_popup";
import { applySiteServiceToPosOrder } from "@pos_advance_order/js/site_service_utils";
import { applyOnsitePledgeLinesToPosOrder } from "@pos_onsite_price/js/onsite_pledge_lines";

export const SERVICE_TYPE = {
    ON_SITE: "on_site",
    CUTTING: "cutting",
    NONE: "none",
};

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

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

export function normalizeServiceType(value) {
    if (value === SERVICE_TYPE.ON_SITE || value === SERVICE_TYPE.CUTTING || value === SERVICE_TYPE.NONE) {
        return value;
    }
    if (value === true) {
        return SERVICE_TYPE.ON_SITE;
    }
    return SERVICE_TYPE.NONE;
}

export function getOnsiteConfig(pos) {
    const configId = pos?.config?.id;
    if (!configId) {
        return null;
    }
    const menus = pos.models?.["pos.onsite.price.menu"]?.getAll?.() || [];
    const menu = menus.find((record) => normalizeId(record.pos_config_id) === configId);
    if (!menu) {
        return null;
    }
    const menuId = normalizeId(menu.id);
    const ranges = (pos.models?.["pos.onsite.price.range"]?.getAll?.() || []).filter(
        (rng) => normalizeId(rng.menu_id) === menuId
    );
    const products = (pos.models?.["pos.onsite.price.product"]?.getAll?.() || []).filter(
        (line) => normalizeId(line.menu_id) === menuId
    );
    return { menu, ranges, products };
}

export function getOnsiteProductLines(order) {
    return (order?.getOrderlines?.() || order?.lines || []).filter((line) => {
        if (line.is_site_service_auto || line.is_onsite_auto_pledge_line) {
            return false;
        }
        const qty = toNumber(line.getQuantity?.() ?? line.qty ?? 0);
        return qty > 0;
    });
}

export function getOnsiteLineProductId(line) {
    const product = line.getProduct?.() || line.product || line.product_id;
    return normalizeId(product?.id || product);
}

const LOG_PREFIX = "[ONSITE]";

export function logOnsite(step, details = {}) {
    console.warn(LOG_PREFIX, step, details);
}

function describeConfig(pos, config) {
    const menuModel = pos?.models?.["pos.onsite.price.menu"];
    const rangeModel = pos?.models?.["pos.onsite.price.range"];
    const productModel = pos?.models?.["pos.onsite.price.product"];
    return {
        posConfigId: pos?.config?.id,
        posConfigName: pos?.config?.name,
        hasMenuModel: Boolean(menuModel),
        hasRangeModel: Boolean(rangeModel),
        hasProductModel: Boolean(productModel),
        menuCount: menuModel?.getAll?.()?.length || 0,
        rangeCount: rangeModel?.getAll?.()?.length || 0,
        productCount: productModel?.getAll?.()?.length || 0,
        matchedMenuId: config?.menu ? normalizeId(config.menu.id) : null,
        matchedProducts: (config?.products || []).map((line) => ({
            id: normalizeId(line.id),
            productId: normalizeId(line.product_id),
            productName: line.product_id?.display_name || line.product_id?.name || "",
            multiple: line.multiple,
        })),
    };
}

function describeOrderProducts(order, config) {
    const productById = getOnsiteProductMultipleMap(config);
    const configuredIds = [...productById.keys()];
    const lines = getOnsiteProductLines(order).map((line) => {
        const productId = getOnsiteLineProductId(line);
        const qty = toNumber(line.getQuantity?.() ?? line.qty ?? 0);
        const multiple = productById.get(productId) || 0;
        const listedInMenu = configuredIds.includes(productId);
        return {
            productId,
            name: line.getProduct?.()?.display_name || line.full_product_name || "",
            qty,
            multiple,
            lineEffectiveQty: listedInMenu ? qty * multiple : 0,
            listedInMenu,
        };
    });
    return {
        lines,
        orderTotalEffectiveQty: computeOrderTotalEffectiveQty(order, productById),
    };
}

export function getSkipReason(order, config, pos) {
    if (!order) {
        return "no_active_order";
    }
    if (!pos?.models?.["pos.onsite.price.menu"]) {
        return "onsite_models_not_loaded_in_pos";
    }
    if (!config) {
        return "no_onsite_menu_for_this_pos";
    }
    if (!menuHasOnsiteProducts(config)) {
        return "products_tab_empty";
    }
    if (!orderHasOnsiteProducts(order, config)) {
        return "cart_has_no_listed_product";
    }
    const state = getOnsiteUiState(order);
    const signature = getOnsiteOrderSignature(order, config);
    if (state?.applied && state?.signature === signature) {
        return "already_answered_for_this_cart";
    }
    return null;
}

export function orderHasOnsiteProducts(order, config) {
    if (!config?.products?.length) {
        return false;
    }
    const productIds = new Set(
        config.products.map((line) => normalizeId(line.product_id)).filter(Boolean)
    );
    return getOnsiteProductLines(order).some((line) => productIds.has(getOnsiteLineProductId(line)));
}

export function getOnsiteOrderSignature(order, config) {
    const productIds = new Set(
        (config?.products || []).map((line) => normalizeId(line.product_id)).filter(Boolean)
    );
    return getOnsiteProductLines(order)
        .map((line) => {
            const productId = getOnsiteLineProductId(line);
            if (!productIds.has(productId)) {
                return null;
            }
            const qty = toNumber(line.getQuantity?.() ?? line.qty ?? 0);
            return `${productId}:${qty}`;
        })
        .filter(Boolean)
        .sort()
        .join("|");
}

export function getOnsiteProductMultipleMap(config) {
    const productById = new Map();
    for (const line of config?.products || []) {
        const productId = normalizeId(line.product_id);
        if (productId) {
            productById.set(productId, toNumber(line.multiple, 0));
        }
    }
    return productById;
}

export function computeOrderTotalEffectiveQty(order, productById) {
    let total = 0;
    for (const line of getOnsiteProductLines(order)) {
        const productId = getOnsiteLineProductId(line);
        if (!productById.has(productId)) {
            continue;
        }
        const qty = toNumber(line.getQuantity?.() ?? line.qty ?? 0);
        total += qty * productById.get(productId);
    }
    return total;
}

function rangeServiceType(rng) {
    if (rng.service_type) {
        return normalizeServiceType(rng.service_type);
    }
    // Legacy boolean field fallback before migration/reload
    return rng.is_on_site ? SERVICE_TYPE.ON_SITE : SERVICE_TYPE.NONE;
}

export function findOnsiteRange(ranges, serviceType, effectiveQty) {
    const type = normalizeServiceType(serviceType);
    return (ranges || []).find((rng) => {
        if (rangeServiceType(rng) !== type) {
            return false;
        }
        const minQty = toNumber(rng.min_qty);
        const maxQty = toNumber(rng.max_qty);
        return effectiveQty >= minQty && effectiveQty <= maxQty;
    });
}

export function applyOnsitePricesToOrder(order, serviceType, config) {
    const type = normalizeServiceType(serviceType);
    const productById = getOnsiteProductMultipleMap(config);
    const orderTotalEffectiveQty = computeOrderTotalEffectiveQty(order, productById);
    const range = findOnsiteRange(config.ranges, type, orderTotalEffectiveQty);
    if (!range) {
        return {
            ok: false,
            error: _t(
                "No on-site price range found for order total (effective qty: %s, type: %s).",
                orderTotalEffectiveQty,
                type
            ),
            orderTotalEffectiveQty,
            serviceType: type,
        };
    }
    const pricePerKilo = toNumber(range.price_per_kilo);
    const changes = [];
    for (const line of getOnsiteProductLines(order)) {
        const productId = getOnsiteLineProductId(line);
        if (!productById.has(productId)) {
            continue;
        }
        const multiple = productById.get(productId);
        const qty = toNumber(line.getQuantity?.() ?? line.qty ?? 0);
        const lineEffectiveQty = qty * multiple;
        const unitPrice = pricePerKilo * multiple;
        if (typeof line.setUnitPrice === "function") {
            line.price_type = "manual";
            line.setUnitPrice(unitPrice);
        } else {
            line.price_unit = unitPrice;
        }
        changes.push({
            productId,
            qty,
            multiple,
            lineEffectiveQty,
            orderTotalEffectiveQty,
            pricePerKilo,
            unitPrice,
            lineAmount: unitPrice * qty,
            serviceType: type,
        });
    }
    return {
        ok: true,
        changes,
        orderTotalEffectiveQty,
        pricePerKilo,
        range,
        serviceType: type,
        servicePrice: toNumber(range.service_price),
        cuttingServicePrice: toNumber(range.cutting_service_price),
    };
}

export function menuHasOnsiteProducts(config) {
    return Boolean(config?.products?.length);
}

export function getOnsiteUiState(order) {
    if (!order) {
        return null;
    }
    if (!order.uiState) {
        order.uiState = {};
    }
    if (!order.uiState.onsitePricing) {
        order.uiState.onsitePricing = {
            applied: false,
            serviceType: SERVICE_TYPE.NONE,
            isOnSite: false,
            servicePrice: 0,
            cuttingServicePrice: 0,
            signature: "",
        };
    }
    return order.uiState.onsitePricing;
}

export function getOrderServiceType(order) {
    const state = order?.uiState?.onsitePricing;
    if (state?.serviceType) {
        return normalizeServiceType(state.serviceType);
    }
    if (order?.onsite_service_type) {
        return normalizeServiceType(order.onsite_service_type);
    }
    if (state?.isOnSite || order?.is_onsite_order) {
        return SERVICE_TYPE.ON_SITE;
    }
    return SERVICE_TYPE.NONE;
}

/** True for Site Service or Cutting (both skip pledge). */
export function isOrderOnSite(order) {
    const type = getOrderServiceType(order);
    return type === SERVICE_TYPE.ON_SITE || type === SERVICE_TYPE.CUTTING;
}

export function shouldPromptOnsitePricing(order, config) {
    if (!order || !menuHasOnsiteProducts(config) || !orderHasOnsiteProducts(order, config)) {
        return false;
    }
    const state = getOnsiteUiState(order);
    const signature = getOnsiteOrderSignature(order, config);
    return !(state?.applied && state?.signature === signature);
}

function storeOnsiteAnswer(order, serviceType, config, priceInfo = {}) {
    const type = normalizeServiceType(serviceType);
    const state = getOnsiteUiState(order);
    if (state) {
        state.applied = true;
        state.serviceType = type;
        state.isOnSite = type === SERVICE_TYPE.ON_SITE || type === SERVICE_TYPE.CUTTING;
        state.servicePrice = toNumber(priceInfo.servicePrice);
        state.cuttingServicePrice = toNumber(priceInfo.cuttingServicePrice);
        state.signature = getOnsiteOrderSignature(order, config);
    }
    if (order?.model?.fields?.is_onsite_order) {
        order.is_onsite_order = type === SERVICE_TYPE.ON_SITE || type === SERVICE_TYPE.CUTTING;
    }
    if (order?.model?.fields?.onsite_service_type) {
        order.onsite_service_type = type;
    }
}

function buildServiceLineOptions(order, serviceType) {
    const type = normalizeServiceType(serviceType);
    const state = getOnsiteUiState(order);
    if (type === SERVICE_TYPE.ON_SITE) {
        return {
            serviceType: type,
            unitPrice: toNumber(state?.servicePrice),
        };
    }
    if (type === SERVICE_TYPE.CUTTING) {
        return {
            serviceType: type,
            unitPrice: toNumber(state?.cuttingServicePrice),
        };
    }
    return { serviceType: SERVICE_TYPE.NONE };
}

async function fetchOnsiteConfigFromServer(pos) {
    const orm = pos?.data?.orm || pos?.env?.services?.orm;
    const configId = pos?.config?.id;
    if (!orm || !configId) {
        logOnsite("server fallback skipped", { hasOrm: Boolean(orm), configId });
        return null;
    }
    try {
        const menus = await orm.searchRead(
            "pos.onsite.price.menu",
            [["pos_config_id", "=", configId]],
            ["id", "name", "pos_config_id"],
            { limit: 1 }
        );
        logOnsite("server fallback menus", { configId, menus });
        if (!menus.length) {
            return null;
        }
        const menu = menus[0];
        const [ranges, products] = await Promise.all([
            orm.searchRead(
                "pos.onsite.price.range",
                [["menu_id", "=", menu.id]],
                [
                    "id",
                    "menu_id",
                    "name",
                    "service_type",
                    "min_qty",
                    "max_qty",
                    "price_per_kilo",
                    "service_price",
                    "cutting_service_price",
                ]
            ),
            orm.searchRead(
                "pos.onsite.price.product",
                [["menu_id", "=", menu.id]],
                ["id", "menu_id", "product_id", "multiple"]
            ),
        ]);
        logOnsite("server fallback lines", {
            rangeCount: ranges.length,
            productCount: products.length,
            products,
        });
        return { menu, ranges, products, fromServer: true };
    } catch (error) {
        logOnsite("server fallback failed", { message: error?.data?.message || error?.message || String(error) });
        return null;
    }
}

export async function promptAndApplyOnsitePricing({
    pos,
    dialog,
    notification,
    stayMessage,
    source = "unknown",
}) {
    const order = pos.getOrder?.() || pos.get_order?.();
    let config = getOnsiteConfig(pos);
    let skipReason = getSkipReason(order, config, pos);
    logOnsite(`${source}: check`, {
        skipReason,
        willPrompt: !skipReason,
        ...describeConfig(pos, config),
        cartProducts: describeOrderProducts(order, config),
        uiState: order?.uiState?.onsitePricing || null,
        hasDialog: Boolean(dialog),
    });
    if (
        skipReason === "no_onsite_menu_for_this_pos" ||
        skipReason === "products_tab_empty"
    ) {
        const fetched = await fetchOnsiteConfigFromServer(pos);
        if (fetched) {
            config = fetched;
            skipReason = getSkipReason(order, config, pos);
            logOnsite(`${source}: check after server fallback`, {
                skipReason,
                willPrompt: !skipReason,
                fromServer: true,
                matchedProducts: (config.products || []).map((line) => ({
                    productId: normalizeId(line.product_id),
                    multiple: line.multiple,
                })),
                cartProducts: describeOrderProducts(order, config),
            });
        }
    }
    if (skipReason) {
        return { skipped: true, reason: skipReason };
    }
    logOnsite(`${source}: opening service-type popup`);
    const payload = await makeAwaitable(dialog, OnSitePricePopup, { pos });
    logOnsite(`${source}: popup result`, payload);
    if (!payload?.serviceType) {
        return { cancelled: true };
    }
    const serviceType = normalizeServiceType(payload.serviceType);
    let changes = [];
    let priceInfo = { servicePrice: 0, cuttingServicePrice: 0 };
    if (config && orderHasOnsiteProducts(order, config)) {
        const result = applyOnsitePricesToOrder(order, serviceType, config);
        if (!result.ok) {
            logOnsite(`${source}: price error`, result);
            notification.add(result.error, { type: "danger" });
            return { error: true };
        }
        changes = result.changes || [];
        priceInfo = {
            servicePrice: result.servicePrice,
            cuttingServicePrice: result.cuttingServicePrice,
        };
    }
    storeOnsiteAnswer(order, serviceType, config, priceInfo);
    logOnsite(`${source}: stored answer`, {
        serviceType,
        priceInfo,
        changes,
        uiState: order?.uiState?.onsitePricing || null,
    });
    if (source === "pay" || source === "pay_fast") {
        const siteServiceResult = await applySiteServiceToPosOrder(
            pos,
            order,
            buildServiceLineOptions(order, serviceType)
        );
        logOnsite(`${source}: site/cutting service`, siteServiceResult);
        if (siteServiceResult.missingProduct) {
            notification.add(
                serviceType === SERVICE_TYPE.CUTTING
                    ? _t("Cutting service product is not available in this Point of Sale.")
                    : _t("Site service product is not available in this Point of Sale."),
                { type: "warning" }
            );
        }
        // Site Service or Cutting → never add pledge.
        // None → add mapped pledge product lines.
        const skipPledge = serviceType === SERVICE_TYPE.ON_SITE || serviceType === SERVICE_TYPE.CUTTING;
        const pledgeResult = await applyOnsitePledgeLinesToPosOrder(pos, order, skipPledge);
        logOnsite(`${source}: onsite pledge lines`, pledgeResult);
        if (!skipPledge) {
            if (pledgeResult.missingMapping) {
                notification.add(
                    _t("Site Service pledge mapping is not loaded. Check Site Service config and reload POS."),
                    { type: "warning" }
                );
            } else if (pledgeResult.missingProducts?.length) {
                notification.add(
                    _t("Mapped pledge product is not loaded in this POS. Open Products, ensure Available in POS, then reload the POS session."),
                    { type: "warning" }
                );
            } else if (pledgeResult.skippedNoAmount?.length) {
                notification.add(
                    _t("Mapped pledge product price is zero. Set Sales Price or Pledge Amount on the pledge product."),
                    { type: "warning" }
                );
            } else if (pledgeResult.added) {
                changes = changes.length ? changes : [{ pledgeLinesAdded: pledgeResult.lineCount }];
            }
        }
    }
    if (changes.length) {
        const onlyPledges =
            changes.length === 1 && changes[0]?.pledgeLinesAdded;
        notification.add(
            onlyPledges
                ? _t("Pledge lines added. Press Payment again to continue.")
                : stayMessage || _t("On-site prices applied. Check the new prices."),
            { type: "success" }
        );
        return { applied: true, serviceType, isOnSite: skipPledgeForType(serviceType), changes };
    }
    return {
        answered: true,
        applied: false,
        serviceType,
        isOnSite: skipPledgeForType(serviceType),
        changes,
    };
}

function skipPledgeForType(serviceType) {
    const type = normalizeServiceType(serviceType);
    return type === SERVICE_TYPE.ON_SITE || type === SERVICE_TYPE.CUTTING;
}
