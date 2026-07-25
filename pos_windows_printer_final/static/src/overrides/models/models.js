/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosDirectPrinter } from "@pos_windows_printer_final/app/printers";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        if (this.company && !this.company.tax_calculation_rounding_method) {
            this.company.tax_calculation_rounding_method = 'round_per_line';
        }
    },

    afterProcessServerData() {
        var self = this;
        return super.afterProcessServerData(...arguments).then(function () {
            if (self.company && !self.company.tax_calculation_rounding_method) {
                self.company.tax_calculation_rounding_method = 'round_per_line';
            }
            if (self.config.other_devices && self.config.direct_printer_id) {
                const printerData = self.models["printer.printer"].get(self.config.direct_printer_id[0] || self.config.direct_printer_id);
                self.hardwareProxy.printer = new PosDirectPrinter({ printer_id: printerData || self.config.direct_printer_id });
            }
        });
    },

    createPrinter(config) {
        if (config.printer_type === "cr_network_printer") {
            const printer_id = this.models["printer.printer"].get(config.printer_id[0] || config.printer_id);
            return new PosDirectPrinter({ printer_id: printer_id });
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
        if (this.pos.hardwareProxy && this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = false;
        }
        const shouldOpenCashbox = (this.order.isPaidWithCash() || this.order.change) &&
            this.pos.config.iface_cashdrawer;

        if (shouldOpenCashbox && this.pos.hardwareProxy && this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = true;
        }
        return await super.finalizeValidation(...arguments);
    },
    async afterOrderValidation() {
        const result = await super.afterOrderValidation(...arguments);
        if (this.pos.hardwareProxy && this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = false;
        }
        return result;
    },
});
