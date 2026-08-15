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

export function shouldPromptOnsitePricing(order, config) {
    if (!order || !menuHasOnsiteProducts(config) || !orderHasOnsiteProducts(order, config)) {
        return false;
    }
    const signature = getOnsiteOrderSignature(order, config);
    return !(order.onsite_pricing_applied && order.onsite_pricing_signature === signature);
}

function storeOnsiteAnswer(order, isOnSite, config) {
    order.onsite_pricing_applied = true;
    order.onsite_pricing_is_on_site = isOnSite;
    order.is_onsite_order = isOnSite;
    order.onsite_pricing_signature = getOnsiteOrderSignature(order, config);
}

export async function promptAndApplyOnsitePricing({
    pos,
    dialog,
    notification,
    stayMessage,
}) {
    const order = pos.getOrder?.() || pos.get_order?.();
    const config = getOnsiteConfig(pos);
    if (!shouldPromptOnsitePricing(order, config)) {
        return { skipped: true };
    }
    const payload = await makeAwaitable(dialog, OnSitePricePopup, { pos });
    if (!payload || typeof payload.isOnSite !== "boolean") {
        return { cancelled: true };
    }
    let changes = [];
    if (config && orderHasOnsiteProducts(order, config)) {
        const result = applyOnsitePricesToOrder(order, payload.isOnSite, config);
        if (!result.ok) {
            notification.add(result.error, { type: "danger" });
            return { error: true };
        }
        changes = result.changes || [];
    }
    storeOnsiteAnswer(order, payload.isOnSite, config);
    if (changes.length) {
        notification.add(
            stayMessage || _t("On-site prices applied. Check the new prices."),
            { type: "success" }
        );
        return { applied: true, isOnSite: payload.isOnSite, changes };
    }
    return { answered: true, applied: false, isOnSite: payload.isOnSite, changes };
}
