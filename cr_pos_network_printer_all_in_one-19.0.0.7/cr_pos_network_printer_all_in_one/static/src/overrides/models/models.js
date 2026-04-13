/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { CrPrinter } from "@cr_pos_network_printer_all_in_one/app/printers";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(PosStore.prototype, {
    afterProcessServerData() {
        var self = this;
        return super.afterProcessServerData(...arguments).then(function () {
            if (self.config.other_devices && self.config.printer_id) {
                self.hardwareProxy.printer = new CrPrinter({ printer_id: self.config.printer_id });
            }
        });
    },

    createPrinter(config) {
        if (config.printer_type === "cr_network_printer") {
            const printer_id = this.models["printer.printer"].get(config.printer_id);
            return new CrPrinter({ printer_id: printer_id });
        } else {
            return super.createPrinter(...arguments);
        }
    },

    cashMove() {
        const res = super.cashMove(...arguments);
        this.hardwareProxy.printer.is_open_cashbox_receipt_print = true;
        return res;
    },
});

patch(OrderPaymentValidation.prototype, {
    async finalizeValidation() {
        if (this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = false;
        }
        const shouldOpenCashbox = (this.order.isPaidWithCash() || this.order.change) &&
            this.pos.config.iface_cashdrawer;

        if (shouldOpenCashbox) {
            if (this.pos.hardwareProxy.printer) {
                this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = true;
            }
        }
        const result = await super.finalizeValidation(...arguments);
        return result;
    },
    async afterOrderValidation() {
        const result = await super.afterOrderValidation(...arguments);

        // Reset cashbox flag after printing is done
        if (this.pos.hardwareProxy.printer) {
            this.pos.hardwareProxy.printer.is_open_cashbox_receipt_print = false;
        }
        return result;
    },
});