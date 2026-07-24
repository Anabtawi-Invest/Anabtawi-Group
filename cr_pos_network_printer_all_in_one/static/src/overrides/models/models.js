/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { HardwareProxy } from "@point_of_sale/app/services/hardware_proxy_service";
import { CrPrinter } from "@cr_pos_network_printer_all_in_one/app/printers";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(PosStore.prototype, {
    afterProcessServerData() {
        var self = this;
        return super.afterProcessServerData(...arguments).then(function () {
            if (self.config.other_devices && self.config.printer_id) {
                // FIX BUG#1: config.printer_id is a raw Many2one integer ID.
                // Resolve it to the full printer.printer model record so that
                // CrPrinter can access .ip, .port, .print_engine_key, etc.
                let printer = self.config.printer_id;
                if (typeof printer !== "object" || printer === null) {
                    printer = self.models["printer.printer"].get(printer);
                }
                if (printer) {
                    self.hardwareProxy.printer = new CrPrinter({ printer_id: printer });
                    console.log("[CrPrinter] Receipt printer initialized:", printer.name,
                        "| Engine Key:", printer.print_engine_key ? "present" : "MISSING");
                } else {
                    console.warn("[CrPrinter] printer_id", self.config.printer_id,
                        "could not be resolved from loaded printer.printer records.");
                }
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
        // FIX: Guard against hardwareProxy.printer being null/undefined
        if (this.hardwareProxy.printer && this.hardwareProxy.printer.is_open_cashbox_receipt_print !== undefined) {
            this.hardwareProxy.printer.is_open_cashbox_receipt_print = true;
        }
        return res;
    },
});

// FIX BUG#1: Patch HardwareProxy.openCashbox to bypass the IoT connection
// status check when a CrPrinter is attached. The base Odoo code checks
// connectionInfo.status and epson_printer_ip, which are irrelevant for
// Creyox printers that communicate via server-side print jobs.
patch(HardwareProxy.prototype, {
    async openCashbox(action = false) {
        if (this.printer && this.printer instanceof CrPrinter) {
            // Creyox printer: skip IoT/Epson connection checks,
            // directly invoke CrPrinter.openCashbox() if cashdrawer is enabled.
            if (this.pos && this.pos.config.iface_cashdrawer) {
                this.printer.openCashbox();
                if (action) {
                    this.pos.logEmployeeMessage(action, "CASH_DRAWER_ACTION");
                }
            }
            return;
        }
        // Non-Creyox printer: use standard IoT/Epson flow
        return super.openCashbox(...arguments);
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