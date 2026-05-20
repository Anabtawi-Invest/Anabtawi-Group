/** @odoo-module **/

/**
 * CustomCakePopup — Odoo 19 / OWL 2 compliant
 *
 * Changes from previous version:
 * [J1] AbstractAwaitablePopup removed in v17 → use Component + makeAwaitable pattern
 * [J2] pos.models["product.product"] → use .find() on the model array correctly
 * [J5] customer_note field (not set_note/set_customer_note)
 * [J6] patch(ProductScreen, ...) not prototype
 * [J8] Inline complex lambdas in templates → moved to named methods
 * [J9] orderline note written via customer_note property
 */

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";

export class CustomCakePopup extends Component {
    static template = "cake_pos.CustomCakePopup";

    // Props passed when opening via popup service
    static props = {
        close: Function,
    };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");

        this.state = useState({
            loading: true,
            error: "",

            // Options loaded from server
            options: {
                sponge: [], cream: [], filling: [],
                decoration: [], disk: [], sugar_paste: [],
            },
            extraFeatures:   [],
            posProductId:    null,

            // Cashier selections
            persons:         "30",
            sponge_id:       null,
            cream_id:        null,
            filling_id:      null,
            decoration_id:   null,
            disk_id:         null,
            use_sugar_paste: false,
            sugar_paste_id:  null,
            customer_name:   "",
            notes:           "",

            // Extra features: keyed by feature ID
            // { [featId]: { type, value (bool/string), optionId } }
            extraSelections: {},

            // Price display
            selling_price: 0,
            total_cost:    0,
            priceLoading:  false,
        });

        onWillStart(async () => {
            await this._loadData();
        });
    }

    // ── Data loading ────────────────────────────────────────────────────────
    async _loadData() {
        try {
            const data = await this.orm.call("cake.config", "get_pos_cake_data", [], {});

            this.state.options.sponge      = data.ingredients?.sponge      || [];
            this.state.options.cream       = data.ingredients?.cream       || [];
            this.state.options.filling     = data.ingredients?.filling     || [];
            this.state.options.decoration  = data.ingredients?.decoration  || [];
            this.state.options.disk        = data.ingredients?.disk        || [];
            this.state.options.sugar_paste = data.ingredients?.sugar_paste || [];
            this.state.extraFeatures       = data.extra_features           || [];
            this.state.posProductId        = data.pos_product_id           || null;

            // Default to first item per category
            const setDefault = (key, cat) => {
                const list = this.state.options[cat];
                if (list.length) this.state[key] = list[0].id;
            };
            setDefault("sponge_id",      "sponge");
            setDefault("cream_id",       "cream");
            setDefault("filling_id",     "filling");
            setDefault("decoration_id",  "decoration");
            setDefault("disk_id",        "disk");
            setDefault("sugar_paste_id", "sugar_paste");

            // Initialise extra selections
            for (const feat of this.state.extraFeatures) {
                this.state.extraSelections[feat.id] = {
                    type:     feat.feature_type,
                    value:    feat.feature_type === "text" ? "" : false,
                    optionId: feat.options?.[0]?.id || null,
                };
            }

            this.state.loading = false;
            await this._recalcPrice();
        } catch (e) {
            this.state.loading = false;
            this.state.error = "تعذّر تحميل البيانات — Could not load cake options.";
            console.error("[CakePopup] load error:", e);
        }
    }

    // ── Price recalculation (RPC on every change) ────────────────────────────
    async _recalcPrice() {
        if (this.state.loading) return;
        this.state.priceLoading = true;
        try {
            const extraList = [];
            for (const feat of this.state.extraFeatures) {
                const sel = this.state.extraSelections[feat.id];
                if (!sel) continue;
                if (feat.feature_type === "checkbox" && sel.value) {
                    extraList.push({ feature_id: feat.id, option_id: null, text_value: null });
                } else if (feat.feature_type === "dropdown" && sel.value && sel.optionId) {
                    extraList.push({ feature_id: feat.id, option_id: sel.optionId, text_value: null });
                } else if (feat.feature_type === "text" && sel.value) {
                    extraList.push({ feature_id: feat.id, option_id: null, text_value: sel.value });
                }
            }

            const result = await this.orm.call("cake.config", "compute_price_rpc", [], {
                persons:          parseInt(this.state.persons),
                sponge_id:        this.state.sponge_id,
                cream_id:         this.state.cream_id,
                filling_id:       this.state.filling_id,
                decoration_id:    this.state.decoration_id,
                disk_id:          this.state.disk_id,
                use_sugar_paste:  this.state.use_sugar_paste,
                sugar_paste_id:   this.state.use_sugar_paste ? this.state.sugar_paste_id : null,
                extra_selections: extraList,
            });

            this.state.total_cost    = result.total_cost;
            this.state.selling_price = result.selling_price;
        } catch (e) {
            console.error("[CakePopup] price recalc error:", e);
        } finally {
            this.state.priceLoading = false;
        }
    }

    // ── Change handlers (named methods — not inline lambdas in template) ─────
    async onChangePersons(ev) {
        this.state.persons = ev.target.value;
        await this._recalcPrice();
    }
    async onChangeSponge(ev) {
        this.state.sponge_id = parseInt(ev.target.value) || null;
        await this._recalcPrice();
    }
    async onChangeCream(ev) {
        this.state.cream_id = parseInt(ev.target.value) || null;
        await this._recalcPrice();
    }
    async onChangeFilling(ev) {
        this.state.filling_id = parseInt(ev.target.value) || null;
        await this._recalcPrice();
    }
    async onChangeDecoration(ev) {
        this.state.decoration_id = parseInt(ev.target.value) || null;
        await this._recalcPrice();
    }
    async onChangeDisk(ev) {
        this.state.disk_id = parseInt(ev.target.value) || null;
        await this._recalcPrice();
    }
    async onToggleSugarPaste(ev) {
        this.state.use_sugar_paste = ev.target.checked;
        await this._recalcPrice();
    }
    async onChangeSugarPaste(ev) {
        this.state.sugar_paste_id = parseInt(ev.target.value) || null;
        await this._recalcPrice();
    }
    onChangeCustomerName(ev) {
        this.state.customer_name = ev.target.value;
    }
    onChangeNotes(ev) {
        this.state.notes = ev.target.value;
    }

    // Extra feature handlers
    async onToggleExtraCheckbox(featId, ev) {
        this._ensureExtraSel(featId, "checkbox");
        this.state.extraSelections[featId].value = ev.target.checked;
        await this._recalcPrice();
    }
    async onToggleExtraDropdown(featId, ev) {
        this._ensureExtraSel(featId, "dropdown");
        this.state.extraSelections[featId].value = ev.target.checked;
        await this._recalcPrice();
    }
    async onChangeExtraDropdownOption(featId, ev) {
        this._ensureExtraSel(featId, "dropdown");
        this.state.extraSelections[featId].optionId = parseInt(ev.target.value) || null;
        await this._recalcPrice();
    }
    onChangeExtraText(featId, ev) {
        this._ensureExtraSel(featId, "text");
        this.state.extraSelections[featId].value = ev.target.value;
    }

    _ensureExtraSel(featId, type) {
        if (!this.state.extraSelections[featId]) {
            this.state.extraSelections[featId] = { type, value: false, optionId: null };
        }
    }

    // ── Template helpers ─────────────────────────────────────────────────────
    getExtraSel(featId) {
        return this.state.extraSelections[featId] || { type: "", value: false, optionId: null };
    }

    get formattedPrice() {
        return this.state.selling_price.toFixed(3);
    }

    // ── Confirm: add to POS cart ─────────────────────────────────────────────
    async onConfirm() {
        const st = this.state;

        if (!st.posProductId) {
            st.error = "منتج POS غير محدد — POS product not configured. Contact manager.";
            return;
        }
        if (st.selling_price <= 0) {
            st.error = "السعر صفر — Price is 0. Check ingredient configuration.";
            return;
        }

        // [J2] Correct way to find a product in Odoo 19 POS model store
        const allProducts = this.pos.models["product.product"].getAll
            ? this.pos.models["product.product"].getAll()
            : Object.values(this.pos.models["product.product"]);
        const product = allProducts.find((p) => p.id === st.posProductId);

        if (!product) {
            st.error = "منتج الجاتو غير موجود في جلسة POS — Custom cake product not found in POS session.";
            return;
        }

        // Build extra features summary
        const extraFeaturesSummary = [];
        const extraFeaturesDisplay = [];
        for (const feat of st.extraFeatures) {
            const sel = st.extraSelections[feat.id];
            if (!sel) continue;
            if (feat.feature_type === "checkbox" && sel.value) {
                extraFeaturesSummary.push({ feature_name: feat.name, value: "نعم / Yes" });
                extraFeaturesDisplay.push(`${feat.name}: نعم`);
            } else if (feat.feature_type === "dropdown" && sel.value && sel.optionId) {
                const opt = (feat.options || []).find((o) => o.id === sel.optionId);
                if (opt) {
                    extraFeaturesSummary.push({ feature_name: feat.name, value: opt.name });
                    extraFeaturesDisplay.push(`${feat.name}: ${opt.name}`);
                }
            } else if (feat.feature_type === "text" && sel.value) {
                extraFeaturesSummary.push({ feature_name: feat.name, value: sel.value });
                extraFeaturesDisplay.push(`${feat.name}: ${sel.value}`);
            }
        }

        // Human-readable receipt note
        const getName = (cat, id) =>
            (st.options[cat] || []).find((o) => o.id === id)?.name || "—";

        const receiptNote = [
            `جاتو مخصص | Custom Cake`,
            `${st.persons} أشخاص`,
            `السبونج: ${getName("sponge", st.sponge_id)}`,
            `الكريما: ${getName("cream", st.cream_id)}`,
            `الحشوة: ${getName("filling", st.filling_id)}`,
            `الزينة: ${getName("decoration", st.decoration_id)}`,
            `الدسك: ${getName("disk", st.disk_id)}`,
            st.use_sugar_paste
                ? `عجينة السكر: ${getName("sugar_paste", st.sugar_paste_id)}`
                : `بدون عجينة سكر`,
            ...extraFeaturesDisplay,
            ...(st.customer_name ? [`الزبون: ${st.customer_name}`] : []),
            ...(st.notes ? [`ملاحظات: ${st.notes}`] : []),
        ].join("\n");

        // JSON payload for backend — parsed in pos_order_inherit._process_order
        const cakeCfgJson = JSON.stringify({
            persons:         st.persons,
            sponge_id:       st.sponge_id,
            cream_id:        st.cream_id,
            filling_id:      st.filling_id,
            decoration_id:   st.decoration_id,
            disk_id:         st.disk_id,
            use_sugar_paste: st.use_sugar_paste,
            sugar_paste_id:  st.sugar_paste_id,
            extra_features:  extraFeaturesSummary,
            customer_name:   st.customer_name,
            notes:           st.notes,
            total_cost:      st.total_cost,
            selling_price:   st.selling_price,
        });

        // Add orderline
        const order = this.pos.get_order();
        order.add_product(product, {
            price:    st.selling_price,
            quantity: 1,
        });

        // [J5][J9] In Odoo 17+ use customer_note (not set_note or note)
        const lastLine = order.get_last_orderline();
        if (lastLine) {
            // Embed the JSON config (read by backend after payment)
            lastLine.customer_note = `CAKE_CFG::${cakeCfgJson}`;
            // Also update the display note for receipt
            if (typeof lastLine.set_customer_note === "function") {
                lastLine.set_customer_note(receiptNote);
            } else {
                lastLine.customer_note = receiptNote + `\nCAKE_CFG::${cakeCfgJson}`;
            }
        }

        this.props.close({ confirmed: true });
    }

    onCancel() {
        this.props.close({ confirmed: false });
    }
}
