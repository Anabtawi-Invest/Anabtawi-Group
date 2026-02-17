/** @odoo-module **/

import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";

export class ScrapPopup extends Component {
    static template = "pos_scrap.ScrapPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        defaultProductId: { type: Number, optional: true },
        defaultQty: { type: Number, optional: true },
        defaultOrigin: { type: String, optional: true },
    };

    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.searchRef = useRef("productSearch");

        this.state = useState({
            loading: true,
            productSearch: "",
            productId: this.props.defaultProductId || null,
            qty: this.props.defaultQty || 1,
            locationId: null,
            scrapLocationId: null,
            validate: true,
            sourceLocations: [],
            scrapLocations: [],
            reasonTags: [],
            selectedReasonTagIds: [],
        });

        onMounted(async () => {
            await Promise.all([this._loadLocations(), this._loadReasons()]);
            this.state.loading = false;
            if (this.searchRef.el) {
                this.searchRef.el.focus();
            }
        });
    }

    get selectedProduct() {
        if (!this.state.productId) {
            return null;
        }
        return this.pos.models["product.product"]?.get(this.state.productId) || null;
    }

    get productMatches() {
        const term = (this.state.productSearch || "").trim().toLowerCase();
        if (!term) {
            return [];
        }
        const products = this.pos.models["product.product"]?.getAll?.() || [];
        const matches = [];
        for (const p of products) {
            const name = (p.display_name || p.name || "").toLowerCase();
            const code = (p.default_code || "").toLowerCase();
            const barcode = (p.barcode || "").toLowerCase();
            if (name.includes(term) || code.includes(term) || barcode.includes(term)) {
                matches.push(p);
            }
            if (matches.length >= 20) {
                break;
            }
        }
        return matches;
    }

    async _loadLocations() {
        const rawCompanyId = this.pos.config.raw?.company_id;
        const companyId =
            this.pos.config.company_id?.id ||
            (Array.isArray(rawCompanyId) ? rawCompanyId[0] : rawCompanyId) ||
            this.pos.company?.id ||
            false;

        const internalDomain = [
            "&",
            ["usage", "=", "internal"],
            "|",
            ["company_id", "=", false],
            ["company_id", "=", companyId],
        ];
        const inventoryDomain = [
            "&",
            ["usage", "=", "inventory"],
            "|",
            ["company_id", "=", false],
            ["company_id", "=", companyId],
        ];

        try {
            const [sourceLocations, scrapLocations] = await Promise.all([
                this.orm.searchRead("stock.location", internalDomain, ["id", "display_name"], {
                    limit: 200,
                }),
                this.orm.searchRead("stock.location", inventoryDomain, ["id", "display_name"], {
                    limit: 200,
                }),
            ]);

            this.state.sourceLocations = sourceLocations || [];
            this.state.scrapLocations = scrapLocations || [];

            // Defaults: source from picking type if possible, else first internal
            const defaultSourceId = await this._getDefaultSourceLocationId();
            this.state.locationId =
                defaultSourceId ||
                this.state.sourceLocations?.[0]?.id ||
                null;

            // Default scrap location: first inventory location
            this.state.scrapLocationId = this.state.scrapLocations?.[0]?.id || null;
        } catch (error) {
            console.error("[POS SCRAP] Error loading locations:", error);
            this.notification.add(
                _t("Failed to load stock locations. Please check your connection."),
                { type: "danger" }
            );
            this.state.sourceLocations = [];
            this.state.scrapLocations = [];
        }
    }

    async _getDefaultSourceLocationId() {
        try {
            const configRes = await this.orm.read("pos.config", [this.pos.config.id], ["picking_type_id"]);
            const pickingTypeId = configRes?.[0]?.picking_type_id?.[0];
            if (!pickingTypeId) {
                return null;
            }
            const ptRes = await this.orm.read(
                "stock.picking.type",
                [pickingTypeId],
                ["default_location_src_id"]
            );
            return ptRes?.[0]?.default_location_src_id?.[0] || null;
        } catch (e) {
            return null;
        }
    }

    async _loadReasons() {
        try {
            const reasons = await this.orm.searchRead(
                "stock.scrap.reason.tag",
                [],
                ["id", "name"],
                { limit: 200 }
            );
            this.state.reasonTags = reasons || [];
        } catch (error) {
            console.error("[POS SCRAP] Error loading scrap reasons:", error);
            this.state.reasonTags = [];
        }
    }

    onSearchInput(ev) {
        this.state.productSearch = ev.target.value || "";
    }

    selectProduct(product) {
        this.state.productId = product?.id || null;
        // Keep search text, but it's usually nicer to clear it after selecting
        this.state.productSearch = "";
    }

    onQtyInput(ev) {
        const v = ev.target.value;
        const n = Number(v);
        this.state.qty = Number.isFinite(n) ? n : 0;
    }

    onSourceLocationChange(ev) {
        this.state.locationId = ev.target.value ? parseInt(ev.target.value) : null;
    }

    onScrapLocationChange(ev) {
        this.state.scrapLocationId = ev.target.value ? parseInt(ev.target.value) : null;
    }

    onValidateToggle(ev) {
        this.state.validate = !!ev.target.checked;
    }

    toggleReasonTag(tagId, ev) {
        const id = Number(tagId);
        if (!id) {
            return;
        }
        const checked = !!ev?.target?.checked;
        const set = new Set(this.state.selectedReasonTagIds || []);
        if (checked) {
            set.add(id);
        } else {
            set.delete(id);
        }
        this.state.selectedReasonTagIds = [...set];
    }

    confirm() {
        if (!this.state.productId) {
            this.notification.add(_t("Product is required."), { type: "warning" });
            return;
        }
        if (!this.state.locationId) {
            this.notification.add(_t("Source location is required."), { type: "warning" });
            return;
        }
        if (!this.state.scrapLocationId) {
            this.notification.add(_t("Scrap location is required."), { type: "warning" });
            return;
        }
        if (!this.state.qty || this.state.qty <= 0) {
            this.notification.add(_t("Quantity must be greater than 0."), { type: "warning" });
            return;
        }

        const origin = this.props.defaultOrigin || this.pos.getOrder()?.name || "";

        this.props.getPayload({
            product_id: this.state.productId,
            scrap_qty: this.state.qty,
            location_id: this.state.locationId,
            scrap_location_id: this.state.scrapLocationId,
            origin,
            validate: this.state.validate,
            scrap_reason_tag_ids: this.state.selectedReasonTagIds || [],
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

