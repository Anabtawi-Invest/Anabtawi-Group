/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { OnSitePricePopup } from "@pos_onsite_price/js/onsite_price_popup";

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
        if (line.is_site_service_auto) {
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
    const configuredIds = (config?.products || [])
        .map((line) => normalizeId(line.product_id))
        .filter(Boolean);
    return getOnsiteProductLines(order).map((line) => {
        const productId = getOnsiteLineProductId(line);
        return {
            productId,
            name: line.getProduct?.()?.display_name || line.full_product_name || "",
            qty: toNumber(line.getQuantity?.() ?? line.qty ?? 0),
            listedInMenu: configuredIds.includes(productId),
        };
    });
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

export function findOnsiteRange(ranges, isOnSite, effectiveQty) {
    return (ranges || []).find((rng) => {
        if (Boolean(rng.is_on_site) !== Boolean(isOnSite)) {
            return false;
        }
        const minQty = toNumber(rng.min_qty);
        const maxQty = toNumber(rng.max_qty);
        return effectiveQty >= minQty && effectiveQty <= maxQty;
    });
}

export function applyOnsitePricesToOrder(order, isOnSite, config) {
    const productById = new Map();
    for (const line of config.products || []) {
        const productId = normalizeId(line.product_id);
        if (productId) {
            productById.set(productId, toNumber(line.multiple, 0));
        }
    }
    const changes = [];
    for (const line of getOnsiteProductLines(order)) {
        const productId = getOnsiteLineProductId(line);
        if (!productById.has(productId)) {
            continue;
        }
        const multiple = productById.get(productId);
        const qty = toNumber(line.getQuantity?.() ?? line.qty ?? 0);
        const effectiveQty = qty * multiple;
        const range = findOnsiteRange(config.ranges, isOnSite, effectiveQty);
        if (!range) {
            const product = line.getProduct?.() || line.product || {};
            const name = product.display_name || product.name || String(productId);
            return {
                ok: false,
                error: _t(
                    "No on-site price range found for %s (effective qty: %s).",
                    name,
                    effectiveQty
                ),
            };
        }
        const unitPrice = toNumber(range.price_per_kilo) * multiple;
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
            effectiveQty,
            pricePerKilo: toNumber(range.price_per_kilo),
            unitPrice,
            lineAmount: unitPrice * qty,
        });
    }
    return { ok: true, changes };
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
            isOnSite: false,
            signature: "",
        };
    }
    return order.uiState.onsitePricing;
}

export function isOrderOnSite(order) {
    return Boolean(order?.uiState?.onsitePricing?.isOnSite || order?.is_onsite_order);
}

export function shouldPromptOnsitePricing(order, config) {
    if (!order || !menuHasOnsiteProducts(config) || !orderHasOnsiteProducts(order, config)) {
        return false;
    }
    const state = getOnsiteUiState(order);
    const signature = getOnsiteOrderSignature(order, config);
    return !(state?.applied && state?.signature === signature);
}

function storeOnsiteAnswer(order, isOnSite, config) {
    const state = getOnsiteUiState(order);
    if (state) {
        state.applied = true;
        state.isOnSite = isOnSite;
        state.signature = getOnsiteOrderSignature(order, config);
    }
    if (order?.model?.fields?.is_onsite_order) {
        order.is_onsite_order = isOnSite;
    }
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
                ["id", "menu_id", "name", "is_on_site", "min_qty", "max_qty", "price_per_kilo"]
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
    logOnsite(`${source}: opening Yes/No popup`);
    const payload = await makeAwaitable(dialog, OnSitePricePopup, { pos });
    logOnsite(`${source}: popup result`, payload);
    if (!payload || typeof payload.isOnSite !== "boolean") {
        return { cancelled: true };
    }
    let changes = [];
    if (config && orderHasOnsiteProducts(order, config)) {
        const result = applyOnsitePricesToOrder(order, payload.isOnSite, config);
        if (!result.ok) {
            logOnsite(`${source}: price error`, result);
            notification.add(result.error, { type: "danger" });
            return { error: true };
        }
        changes = result.changes || [];
    }
    storeOnsiteAnswer(order, payload.isOnSite, config);
    logOnsite(`${source}: stored answer`, {
        isOnSite: payload.isOnSite,
        changes,
        uiState: order?.uiState?.onsitePricing || null,
    });
    if (changes.length) {
        notification.add(
            stayMessage || _t("On-site prices applied. Check the new prices."),
            { type: "success" }
        );
        return { applied: true, isOnSite: payload.isOnSite, changes };
    }
    return { answered: true, applied: false, isOnSite: payload.isOnSite, changes };
}
