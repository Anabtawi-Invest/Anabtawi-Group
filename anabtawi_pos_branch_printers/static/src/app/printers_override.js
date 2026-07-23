/** @odoo-module */

import { CrPrinter } from "@cr_pos_network_printer_all_in_one/app/printers";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";

patch(CrPrinter.prototype, {
    setup({ printer_id, pos_config_id }) {
        super.setup(...arguments);
        this.pos_config_id = pos_config_id;
    },

    async openCashbox() {
        const print_engine_key = this.printer_id.print_engine_key || '';
        try {
            const result = await rpc('/web/dataset/call_kw', {
                model: 'print.job',
                method: 'create',
                args: [{
                    ip: this.printer_id.ip,
                    port: parseInt(this.printer_id.port),
                    printer_name: this.printer_id.name || '',
                    printer_type: this.printer_id.printer_type || 'network',
                    image_data: false,
                    print_engine_key: print_engine_key,
                    is_open_cashbox: true,
                    pos_config_id: this.pos_config_id,
                }],
                kwargs: {},
            });
            return { result, printerErrorCode: false };
        } catch (err) {
            console.error('[openCashbox] Failed:', err);
            return { result: false, printerErrorCode: err.message };
        }
    },

    async sendPrintingJob(img) {
        if (!this.printer_id) {
            return false;
        }
        let open_cashdrawer = this.is_open_cashbox_receipt_print;
        if (open_cashdrawer) {
            this.is_open_cashbox_receipt_print = false;
        }

        const print_engine_key = this.printer_id.print_engine_key || '';
        try {
            const result = await rpc('/web/dataset/call_kw', {
                model: 'print.job',
                method: 'create',
                args: [{
                    ip: this.printer_id.ip,
                    port: parseInt(this.printer_id.port),
                    printer_name: this.printer_id.name || '',
                    printer_type: this.printer_id.printer_type || 'network',
                    image_data: img,
                    print_engine_key: print_engine_key,
                    is_open_cashbox: open_cashdrawer,
                    pos_config_id: this.pos_config_id,
                }],
                kwargs: {},
            });
            return { result, printerErrorCode: false };
        } catch (err) {
            console.error("Print job failed:", err);
            return { result: false, printerErrorCode: err.message };
        }
    }
});

patch(PosStore.prototype, {
    createPrinter(config) {
        if (config.printer_type === "cr_network_printer") {
            const printer_id = this.models["printer.printer"].get(config.printer_id);
            return new CrPrinter({ printer_id: printer_id, pos_config_id: this.config.id });
        } else {
            return super.createPrinter(...arguments);
        }
    }
});
