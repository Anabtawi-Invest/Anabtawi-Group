/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosDirectPrinter } from "@pos_windows_printer_final/app/printers";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(PosStore.prototype, {
    async processServerData(loadedData) {
        if (loadedData) {
            let defaultCurrencyId = null;
            if (loadedData["res.currency"]) {
                const currencies = Array.isArray(loadedData["res.currency"])
                    ? loadedData["res.currency"]
                    : Object.values(loadedData["res.currency"]);
                if (currencies.length > 0) {
                    defaultCurrencyId = currencies[0].id || currencies[0];
                }
            }

            if (loadedData["res.company"]) {
                const companies = Array.isArray(loadedData["res.company"])
                    ? loadedData["res.company"]
                    : Object.values(loadedData["res.company"]);
                for (const comp of companies) {
                    if (!comp.tax_calculation_rounding_method) {
                        comp.tax_calculation_rounding_method = "round_per_line";
                    }
                    if (!comp.currency_id && defaultCurrencyId) {
                        comp.currency_id = defaultCurrencyId;
                    }
                }
            }

            if (loadedData["pos.config"]) {
                const configs = Array.isArray(loadedData["pos.config"])
                    ? loadedData["pos.config"]
                    : Object.values(loadedData["pos.config"]);
                for (const cfg of configs) {
                    if (cfg.use_pricelist === undefined) {
                        cfg.use_pricelist = false;
                    }
                    if (!cfg.trusted_config_ids || !Array.isArray(cfg.trusted_config_ids)) {
                        cfg.trusted_config_ids = [];
                    }
                }
            }
        }

        const res = await super.processServerData(...arguments);

        if (this.company) {
            if (!this.company.tax_calculation_rounding_method) {
                this.company.tax_calculation_rounding_method = 'round_per_line';
            }
            if (!this.company.currency_id && this.currency) {
                this.company.currency_id = this.currency.id || this.currency;
            }
        }

        if (this.config && this.config.direct_printer_id) {
            let printerData = null;
            if (this.models && this.models["printer.printer"]) {
                printerData = this.models["printer.printer"].get(this.config.direct_printer_id[0] || this.config.direct_printer_id);
            }
            if (this.hardwareProxy) {
                this.hardwareProxy.printer = new PosDirectPrinter({ printer_id: printerData || this.config.direct_printer_id });
            }
        }

        return res;
    },

    createPrinter(config) {
        if (config && config.printer_type === "cr_network_printer") {
            let printer_id = config.printer_id;
            if (this.models && this.models["printer.printer"]) {
                printer_id = this.models["printer.printer"].get(config.printer_id[0] || config.printer_id);
            }
            return new PosDirectPrinter({ printer_id: printer_id || config.printer_id });
        } else {
            return super.createPrinter(...arguments);
        }
    },

    cashMove() {
        const res = super.cashMove(...arguments);
        if (this.hardwareProxy && this.hardwareProxy.printer) {
            this.hardwareProxy.printer.is_open_cashbox_receipt_print = true;
        }
        return res;
    },
});

patch(OrderPaymentValidation.prototype, {
    async finalizeValidation() {
        if (this.pos && this.pos.hardwareProxy && this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = false;
        }
        const shouldOpenCashbox = (this.order.isPaidWithCash() || this.order.change) &&
            this.pos && this.pos.config && this.pos.config.iface_cashdrawer;

        if (shouldOpenCashbox && this.pos && this.pos.hardwareProxy && this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = true;
        }
        return await super.finalizeValidation(...arguments);
    },
    async afterOrderValidation() {
        const result = await super.afterOrderValidation(...arguments);
        if (this.pos && this.pos.hardwareProxy && this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = false;
        }
        return result;
    },
});
