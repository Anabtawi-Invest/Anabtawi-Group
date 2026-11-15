/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AdvanceOrderFormPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup";
import {
    getSiteServiceConfig,
    resolveSiteServiceConfig,
} from "@pos_advance_order/js/site_service_utils";

function advancePopupCacheKey(pos, companyId) {
    const db = odoo.info?.db || "";
    const configId = pos?.config?.id || 0;
    const company = companyId || pos?.company?.id || 0;
    return `pos_advance_popup_cache_${db}_${configId}_${company}`;
}

function readAdvancePopupCache(key) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) {
            return null;
        }
        const data = JSON.parse(raw);
        if (!data || typeof data !== "object" || !data.popupData) {
            return null;
        }
        return data;
    } catch {
        return null;
    }
}

function writeAdvancePopupCache(key, data) {
    try {
        localStorage.setItem(
            key,
            JSON.stringify({
                ...data,
                saved_at: new Date().toISOString(),
            })
        );
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save the advance form lists:", error);
    }
}

function applyAdvancePopupData(popup, popupData, siteServiceConfig) {
    popup.state.discounts = popupData?.discounts || [];
    popup.state.pos_configs = popupData?.pos_configs || [];
    popup.state.from_pos_config_id = popup.props.posConfigId || popup.state.from_pos_config_id;
    popup.state.site_service_config = siteServiceConfig || null;
    popup.state.site_service_available = !!siteServiceConfig;
    if (!popup.state.from_pos_config_id && popup.state.pos_configs.length) {
        popup.state.from_pos_config_id = popup.state.pos_configs[0].id;
    }
    if (
        popup.state.pos_configs.length &&
        !popup.state.pos_configs.some((cfg) => cfg.id === popup.state.picking_pos_config_id)
    ) {
        popup.state.picking_pos_config_id = popup.state.pos_configs[0].id;
    }
    popup._syncPricelistName();
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        // Save the advance form lists while the register still has a connection.
        this.refreshAdvancePopupCache();
        return result;
    },

    advancePopupCacheKey(companyId) {
        return advancePopupCacheKey(this, companyId);
    },

    async refreshAdvancePopupCache() {
        const companyId = this.company?.id || false;
        const key = this.advancePopupCacheKey(companyId);
        try {
            const popupData = await rpc("/pos/advance_order_popup_data", {
                company_id: companyId || false,
            });
            let siteServiceConfig = null;
            try {
                siteServiceConfig =
                    getSiteServiceConfig(this) ||
                    (await resolveSiteServiceConfig(this, this.data?.orm));
            } catch (error) {
                console.warn("[LOCAL_BACKUP] Could not save site service for advances:", error);
                siteServiceConfig = getSiteServiceConfig(this);
            }
            writeAdvancePopupCache(key, { popupData, siteServiceConfig });
            console.info("[LOCAL_BACKUP] Advance form lists saved for offline use.");
        } catch (error) {
            if (readAdvancePopupCache(key)) {
                console.info(
                    "[LOCAL_BACKUP] Could not refresh advance form lists; keeping the last saved copy."
                );
            } else {
                console.warn("[LOCAL_BACKUP] Advance form lists were not saved:", error);
            }
        }
    },
});

patch(AdvanceOrderFormPopup.prototype, {
    async _loadPopupData() {
        const companyId = this.props.companyId || false;
        const key = advancePopupCacheKey(this.props.pos, companyId);
        try {
            const popupData = await rpc("/pos/advance_order_popup_data", {
                company_id: companyId || false,
            });
            const siteServiceConfig = await resolveSiteServiceConfig(this.props.pos, this.orm);
            applyAdvancePopupData(this, popupData, siteServiceConfig);
            writeAdvancePopupCache(key, { popupData, siteServiceConfig });
        } catch (error) {
            const cached = readAdvancePopupCache(key);
            if (cached?.popupData) {
                applyAdvancePopupData(
                    this,
                    cached.popupData,
                    cached.siteServiceConfig || getSiteServiceConfig(this.props.pos)
                );
                this.notification.add(
                    _t("Using the lists saved when this register opened."),
                    { type: "warning" }
                );
                return;
            }
            this.notification.add(
                error?.message || _t("Failed to load popup data."),
                { type: "danger" }
            );
        }
    },
});
