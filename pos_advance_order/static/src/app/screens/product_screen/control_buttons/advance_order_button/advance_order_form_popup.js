/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { getSiteServiceConfig, resolveSiteServiceConfig } from "@pos_advance_order/js/site_service_utils";

/** Same filtering idea as PaymentScreen (minimal + pay_later) plus exclusions for advances. */
export function getAdvanceEligiblePaymentMethods(pos) {
    if (!pos?.config?.payment_method_ids) {
        return [];
    }
    const cashier = pos.cashier;
    const role = cashier?._role;
    const list = [...pos.config.payment_method_ids]
        .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))
        .filter((pm) => {
            if (role === "minimal" && pm.type === "pay_later") {
                return false;
            }
            if (pm.type === "pay_later") {
                return false;
            }
            if (pm.payment_method_type && pm.payment_method_type !== "none") {
                return false;
            }
            return true;
        });
    return list;
}

export class AdvanceOrderFormPopup extends Component {
    static template = "pos_advance_order.AdvanceOrderFormPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: Object,
        posConfigId: { type: Number, optional: true },
        companyId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const paymentMethods = getAdvanceEligiblePaymentMethods(this.props.pos);
        const defaultPmId = paymentMethods.length ? paymentMethods[0].id : null;

        this.state = useState({
            loading: true,
            advance_amount_str: "",
            amount_tendered_str: "",
            selected_payment_method_id: defaultPmId,
            from_pos_config_id: this.props.posConfigId || null,
            picking_pos_config_id: this.props.posConfigId || null,
            pricelist_name: "",
            discount_id: null,
            discounts: [],
            pos_configs: [],
            payment_methods: paymentMethods,
            site_service: false,
            site_service_available: false,
            site_service_config: null,
        });

        onMounted(async () => {
            await this._loadPopupData();
            this.state.loading = false;
        });
    }

    _parseAmount(value) {
        const normalized = String(value ?? "")
            .trim()
            .replace(",", ".");
        if (!normalized) {
            return 0;
        }
        const parsed = parseFloat(normalized);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    get advanceAmount() {
        return this._parseAmount(this.state.advance_amount_str);
    }

    get amountTendered() {
        return this._parseAmount(this.state.amount_tendered_str);
    }

    paymentMethodIconSrc(pm) {
        if (!pm) {
            return "";
        }
        if (pm.image) {
            return `/web/image/pos.payment.method/${pm.id}/image`;
        }
        if (pm.type === "cash") {
            return "/point_of_sale/static/src/img/money.png";
        }
        return "/point_of_sale/static/src/img/card-bank.png";
    }

    advanceAmountFmt() {
        const currencyId = this.props.pos?.currency?.id;
        return formatCurrency(this.advanceAmount, currencyId);
    }

    amountTenderedFmt() {
        const currencyId = this.props.pos?.currency?.id;
        return formatCurrency(this.amountTendered, currencyId);
    }

    changeDueFmt() {
        const currencyId = this.props.pos?.currency?.id;
        const change = Math.max(this.amountTendered - this.advanceAmount, 0);
        return formatCurrency(change, currencyId);
    }

    changeDueRaw() {
        return Math.max(this.amountTendered - this.advanceAmount, 0);
    }

    isPaymentSelected(pm) {
        return pm.id === this.state.selected_payment_method_id;
    }

    paymentMethodRowClass(pm) {
        const selected = this.isPaymentSelected(pm);
        return (
            `button paymentmethod btn btn-secondary btn-lg lh-lg d-flex justify-content-between align-items-center flex-fill text-start ${selected ? "border border-3 border-primary" : "opacity-75"}`
        );
    }

    selectPaymentMethod(pm) {
        this.state.selected_payment_method_id = pm.id;
    }

    async _loadPopupData() {
        const companyId = this.props.companyId || false;
        const discountDomain = [["active", "=", true]];
        if (companyId) {
            discountDomain.push(["company_id", "=", companyId]);
        }
        try {
            const [discounts, posConfigs] = await Promise.all([
                this.orm.searchRead(
                    "pos.advance.discount",
                    discountDomain,
                    ["id", "name", "discount_type", "value"],
                    { limit: 200 }
                ),
                this.orm.searchRead(
                    "pos.config",
                    [],
                    ["id", "name", "pricelist_id", "enable_advance_order"],
                    { limit: 200 }
                ),
            ]);
            this.state.discounts = discounts || [];
            this.state.pos_configs = posConfigs || [];
            this.state.from_pos_config_id = this.props.posConfigId || this.state.from_pos_config_id;
            const siteServiceConfig = await resolveSiteServiceConfig(this.props.pos, this.orm);
            this.state.site_service_config = siteServiceConfig;
            this.state.site_service_available = !!siteServiceConfig;
            if (!this.state.from_pos_config_id && this.state.pos_configs.length) {
                this.state.from_pos_config_id = this.state.pos_configs[0].id;
            }
            if (
                this.state.pos_configs.length &&
                !this.state.pos_configs.some((cfg) => cfg.id === this.state.picking_pos_config_id)
            ) {
                this.state.picking_pos_config_id = this.state.pos_configs[0].id;
            }
            this._syncPricelistName();
        } catch (error) {
            this.notification.add(
                error?.message || _t("Failed to load popup data."),
                { type: "danger" }
            );
        }
    }

    _syncPricelistName() {
        const picked = (this.state.pos_configs || []).find(
            (cfg) => cfg.id === this.state.picking_pos_config_id
        );
        this.state.pricelist_name = picked?.pricelist_id?.[1] || "";
    }

    get currentFromPosName() {
        const fromPos = (this.state.pos_configs || []).find(
            (cfg) => cfg.id === this.state.from_pos_config_id
        );
        return fromPos?.name || "";
    }

    onAdvanceAmountInput(ev) {
        this.state.advance_amount_str = ev.target.value;
    }

    onAmountTenderedInput(ev) {
        this.state.amount_tendered_str = ev.target.value;
    }

    onAdvanceAmountBlur() {
        const advance = this.advanceAmount;
        if (advance > 0) {
            this.state.advance_amount_str = String(advance);
        }
        const tendered = this.amountTendered;
        if (tendered > 0 && tendered < advance) {
            this.state.amount_tendered_str = String(advance);
        }
    }

    onAmountTenderedBlur() {
        const tendered = this.amountTendered;
        if (tendered > 0) {
            this.state.amount_tendered_str = String(tendered);
        }
    }

    onPickingPosChange(ev) {
        this.state.picking_pos_config_id = ev.target.value ? parseInt(ev.target.value, 10) : null;
        this._syncPricelistName();
    }

    onDiscountChange(ev) {
        this.state.discount_id = ev.target.value ? parseInt(ev.target.value, 10) : null;
    }

    onSiteServiceChange(ev) {
        this.state.site_service = ev.target.checked;
    }

    get siteServiceUnavailableText() {
        return _t(
            "Site Service is not enabled. Go to Point of Sale → Site Service and enable it with a service product."
        );
    }

    get discountLabelSuffix() {
        return (discount) =>
            discount.discount_type === "percent"
                ? `${discount.value}%`
                : `${discount.value}`;
    }

    get noEligiblePaymentMethodsText() {
        return _t(
            "No eligible payment methods on this POS. Add manual cash or bank methods without terminal or QR integration in the Point of Sale configuration."
        );
    }

    confirm() {
        const advance = this.advanceAmount;
        const tendered = this.amountTendered;
        if (!advance || advance <= 0) {
            this.notification.add(_t("Advance amount must be greater than zero."), { type: "warning" });
            return;
        }
        const currentFromPosId = this.props.posConfigId || this.state.from_pos_config_id;
        if (!currentFromPosId) {
            this.notification.add(_t("Please select From POS."), { type: "warning" });
            return;
        }
        if (!this.state.picking_pos_config_id) {
            this.notification.add(_t("Please select Picking POS."), { type: "warning" });
            return;
        }
        if (!this.state.selected_payment_method_id) {
            this.notification.add(_t("Please select a payment method."), { type: "warning" });
            return;
        }
        const tenderedFinal = tendered >= advance ? tendered : advance;
        if (tendered < advance) {
            this.notification.add(
                _t("Amount tendered cannot be less than the advance amount."),
                { type: "warning" }
            );
            return;
        }
        if (this.state.site_service && !this.state.site_service_available) {
            this.notification.add(this.siteServiceUnavailableText, { type: "warning" });
            return;
        }
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            advance_amount: advance,
            amount_tendered: tenderedFinal,
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || "",
            from_pos_config_id: currentFromPosId,
            pos_config_id: this.state.picking_pos_config_id,
            discount_id: this.state.discount_id || false,
            site_service: this.state.site_service,
            site_service_config: this.state.site_service_config,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
