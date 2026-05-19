/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { useState, onWillStart } from "@odoo/owl";

/**
 * CustomCakePopup
 * ───────────────
 * Full custom cake configurator in POS.
 * - Cashier fills dropdowns: size, sponge, cream, filling, decoration, disk,
 *   optional sugar paste, optional extra features (figures, candles, etc.)
 * - Selling price is calculated live via RPC on every change
 * - Cost is NEVER shown to the cashier
 * - On confirm: adds an orderline at the computed selling price
 *   with CAKE_CFG:: JSON embedded in the note for backend processing
 */
export class CustomCakePopup extends AbstractAwaitablePopup {
    static template = "cake_pos.CustomCakePopup";
    static defaultProps = { confirmKey: false };

    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");

        this.state = useState({
            // Loading state
            loading: true,
            error: "",

            // Options loaded from server
            options: {
                sponge: [], cream: [], filling: [],
                decoration: [], disk: [], sugar_paste: [],
            },
            extraFeatures: [],
            posProductId: null,

            // Cashier selections
            persons:        "30",
            sponge_id:      null,
            cream_id:       null,
            filling_id:     null,
            decoration_id:  null,
            disk_id:        null,
            use_sugar_paste: false,
            sugar_paste_id: null,
            customer_name:  "",
            notes:          "",

            // Extra feature selections: {featureId: {type, value, optionId}}
            extraSelections: {},

            // Computed price (shown to cashier)
            selling_price: 0,
            total_cost:    0,
            priceLoading:  false,
        });

        onWillStart(async () => {
            await this._loadData();
        });
    }

    // ── Data loading ──────────────────────────────────────────────────────────
    async _loadData() {
        try {
            const data = await this.orm.call("cake.config", "get_pos_cake_data", [], {});

            this.state.options.sponge     = data.ingredients.sponge      || [];
            this.state.options.cream      = data.ingredients.cream       || [];
            this.state.options.filling    = data.ingredients.filling     || [];
            this.state.options.decoration = data.ingredients.decoration  || [];
            this.state.options.disk       = data.ingredients.disk        || [];
            this.state.options.sugar_paste= data.ingredients.sugar_paste || [];
            this.state.extraFeatures      = data.extra_features          || [];
            this.state.posProductId       = data.pos_product_id          || null;

            // Default: first item in each list
            const setDefault = (key, cat) => {
                if (this.state.options[cat].length)
                    this.state[key] = this.state.options[cat][0].id;
            };
            setDefault("sponge_id",     "sponge");
            setDefault("cream_id",      "cream");
            setDefault("filling_id",    "filling");
            setDefault("decoration_id", "decoration");
            setDefault("disk_id",       "disk");
            setDefault("sugar_paste_id","sugar_paste");

            // Default extra selections
            for (const feat of this.state.extraFeatures) {
                if (feat.feature_type === "checkbox") {
                    this.state.extraSelections[feat.id] = { type: "checkbox", value: false, optionId: null };
                } else if (feat.feature_type === "dropdown") {
                    const firstOpt = feat.options[0] || null;
                    this.state.extraSelections[feat.id] = {
                        type: "dropdown", value: false, optionId: firstOpt ? firstOpt.id : null,
                    };
                } else {
                    this.state.extraSelections[feat.id] = { type: "text", value: "", optionId: null };
                }
            }

            this.state.loading = false;
            await this._recalcPrice();
        } catch (e) {
            this.state.loading = false;
            this.state.error = "تعذّر تحميل البيانات — Could not load cake options. Check server.";
            console.error("CustomCakePopup load error:", e);
        }
    }

    // ── Price recalculation ───────────────────────────────────────────────────
    async _recalcPrice() {
        if (this.state.loading) return;
        this.state.priceLoading = true;
        try {
            // Build extra_selections list for RPC
            const extraList = [];
            for (const feat of this.state.extraFeatures) {
                const sel = this.state.extraSelections[feat.id];
                if (!sel) continue;
                if (feat.feature_type === "checkbox" && sel.value) {
                    extraList.push({ feature_id: feat.id, option_id: null, text_value: null });
                } else if (feat.feature_type === "dropdown" && sel.optionId) {
                    extraList.push({ feature_id: feat.id, option_id: sel.optionId, text_value: null });
                } else if (feat.feature_type === "text" && sel.value) {
                    extraList.push({ feature_id: feat.id, option_id: null, text_value: sel.value });
                }
            }

            const result = await this.orm.call("cake.config", "compute_price_rpc", [], {
                persons:         parseInt(this.state.persons),
                sponge_id:       this.state.sponge_id,
                cream_id:        this.state.cream_id,
                filling_id:      this.state.filling_id,
                decoration_id:   this.state.decoration_id,
                disk_id:         this.state.disk_id,
                use_sugar_paste: this.state.use_sugar_paste,
                sugar_paste_id:  this.state.use_sugar_paste ? this.state.sugar_paste_id : null,
                extra_selections: extraList,
            });

            this.state.total_cost    = result.total_cost;
            this.state.selling_price = result.selling_price;
        } catch (e) {
            console.error("Price recalc error:", e);
        } finally {
            this.state.priceLoading = false;
        }
    }

    // ── Change handlers ───────────────────────────────────────────────────────
    async onChange(field, ev) {
        this.state[field] = ev.target.value;
        await this._recalcPrice();
    }
    async onChangeInt(field, ev) {
        const v = parseInt(ev.target.value);
        this.state[field] = isNaN(v) ? null : v;
        await this._recalcPrice();
    }
    async onToggleSugarPaste(ev) {
        this.state.use_sugar_paste = ev.target.checked;
        await this._recalcPrice();
    }
    onChangeText(field, ev) {
        this.state[field] = ev.target.value;
    }

    // Extra feature handlers
    async onToggleExtraCheckbox(featId, ev) {
        if (!this.state.extraSelections[featId])
            this.state.extraSelections[featId] = { type: "checkbox", value: false, optionId: null };
        this.state.extraSelections[featId].value = ev.target.checked;
        await this._recalcPrice();
    }
    async onChangeExtraDropdown(featId, ev) {
        const optId = parseInt(ev.target.value) || null;
        if (!this.state.extraSelections[featId])
            this.state.extraSelections[featId] = { type: "dropdown", value: true, optionId: null };
        this.state.extraSelections[featId].optionId = optId;
        this.state.extraSelections[featId].value = true;
        await this._recalcPrice();
    }
    onChangeExtraText(featId, ev) {
        if (!this.state.extraSelections[featId])
            this.state.extraSelections[featId] = { type: "text", value: "", optionId: null };
        this.state.extraSelections[featId].value = ev.target.value;
    }

    // ── Confirm: add to POS cart ──────────────────────────────────────────────
    async confirm() {
        const st = this.state;

        if (!st.posProductId) {
            st.error = "لم يتم تحديد منتج POS — POS product not configured. Contact manager.";
            return;
        }
        if (st.selling_price <= 0) {
            st.error = "السعر صفر — Selling price is 0. Check ingredient configuration.";
            return;
        }

        // Find product in POS models
        const product = this.pos.models["product.product"].find(p => p.id === st.posProductId);
        if (!product) {
            st.error = "منتج الجاتو غير موجود في POS — Custom cake product not found in POS session.";
            return;
        }

        // Build extra features summary for display & for storage
        const extraFeaturesSummary = [];
        const extraFeaturesDisplay = [];
        for (const feat of st.extraFeatures) {
            const sel = st.extraSelections[feat.id];
            if (!sel) continue;
            if (feat.feature_type === "checkbox" && sel.value) {
                extraFeaturesSummary.push({ feature_name: feat.name, value: "نعم / Yes" });
                extraFeaturesDisplay.push(`⭐ ${feat.name}: نعم`);
            } else if (feat.feature_type === "dropdown" && sel.optionId) {
                const opt = (feat.options || []).find(o => o.id === sel.optionId);
                if (opt) {
                    extraFeaturesSummary.push({ feature_name: feat.name, value: opt.name });
                    extraFeaturesDisplay.push(`⭐ ${feat.name}: ${opt.name}`);
                }
            } else if (feat.feature_type === "text" && sel.value) {
                extraFeaturesSummary.push({ feature_name: feat.name, value: sel.value });
                extraFeaturesDisplay.push(`⭐ ${feat.name}: ${sel.value}`);
            }
        }

        // Human-readable receipt note
        const getName = (cat, id) =>
            (st.options[cat] || []).find(o => o.id === id)?.name || "—";

        const receiptLines = [
            `🎂 جاتو مخصص | Custom Cake`,
            `👥 ${st.persons} أشخاص`,
            `🍰 ${getName("sponge", st.sponge_id)}`,
            `🍦 ${getName("cream", st.cream_id)}`,
            `🍓 ${getName("filling", st.filling_id)}`,
            `🎨 ${getName("decoration", st.decoration_id)}`,
            `📀 ${getName("disk", st.disk_id)}`,
            st.use_sugar_paste
                ? `🍬 ${getName("sugar_paste", st.sugar_paste_id)}`
                : `🍬 بدون عجينة سكر`,
            ...extraFeaturesDisplay,
            ...(st.customer_name ? [`👤 ${st.customer_name}`] : []),
            ...(st.notes ? [`📝 ${st.notes}`] : []),
        ].join("\n");

        // JSON payload embedded in note — parsed by pos_order_inherit.py after payment
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

        // Add product to order
        const order = this.pos.get_order();
        order.add_product(product, {
            price:    st.selling_price,
            quantity: 1,
        });

        const lastLine = order.get_last_orderline();
        if (lastLine) {
            lastLine.set_note(`CAKE_CFG::${cakeCfgJson}`);
            // Set a clean display description (visible to cashier on receipt)
            if (lastLine.set_customer_note) {
                lastLine.set_customer_note(receiptLines);
            }
        }

        this.confirm_value = true;
        super.confirm();
    }

    cancel() {
        super.cancel();
    }

    // ── Template helpers ──────────────────────────────────────────────────────
    get formattedPrice() {
        return this.state.selling_price.toFixed(3);
    }

    getExtraSel(featId) {
        return this.state.extraSelections[featId] || {};
    }
}
