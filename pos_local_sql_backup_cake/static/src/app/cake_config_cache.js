/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { CustomCakeFormPopup } from "@pos_custom_cake/app/screens/product_screen/control_buttons/cake_button/custom_cake_form_popup";

export function cakeConfigCacheKey(pos) {
    return `pos_cake_config_cache_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

export function readCakeConfigCache(pos) {
    try {
        const raw = localStorage.getItem(cakeConfigCacheKey(pos));
        const data = JSON.parse(raw || "null");
        return data?.config || null;
    } catch {
        return null;
    }
}

export function writeCakeConfigCache(pos, config) {
    try {
        localStorage.setItem(
            cakeConfigCacheKey(pos),
            JSON.stringify({
                config: config || null,
                saved_at: new Date().toISOString(),
            })
        );
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save cake config cache:", error);
    }
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.refreshCakeConfigCache();
        return result;
    },

    async refreshCakeConfigCache() {
        if (!this.config?.id || this.config.enable_custom_cake === false) {
            return null;
        }
        try {
            const config = await rpc("/pos/custom_cake/get_config", {
                pos_config_id: this.config.id,
            });
            if (config) {
                writeCakeConfigCache(this, config);
            }
            return config;
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not refresh cake config cache:", error);
            return readCakeConfigCache(this);
        }
    },
});

patch(CustomCakeFormPopup.prototype, {
    async _loadConfig() {
        try {
            const config = await rpc("/pos/custom_cake/get_config", {
                pos_config_id: this.props.pos.config.id,
            });
            this.state.config = config;
            writeCakeConfigCache(this.props.pos, config);
        } catch (error) {
            const cached = readCakeConfigCache(this.props.pos);
            if (cached) {
                this.state.config = cached;
                this.notification.add(
                    error?.message
                        ? `${error.message} (using cached cake config)`
                        : "Using cached cake configuration (offline).",
                    { type: "warning" }
                );
                return;
            }
            this.notification.add(error?.message || "Failed to load cake configuration.", {
                type: "danger",
            });
        }
    },
});
