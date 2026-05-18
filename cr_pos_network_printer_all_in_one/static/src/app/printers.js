/* @odoo-module */

import { BasePrinter } from "@point_of_sale/app/utils/printer/base_printer";
import { rpc } from "@web/core/network/rpc";

export class CrPrinter extends BasePrinter {
    setup({ printer_id }) {
        super.setup(...arguments);
        this.printer_id = printer_id;
    }

    /**
     * @override
     */
    async openCashbox() {
        console.log('[openCashbox] Called');

        const print_engine_key = this.printer_id.print_engine_key || '';
        console.log('[openCashbox] Printer details:', {
            ip: this.printer_id.ip,
            port: this.printer_id.port,
            name: this.printer_id.name,
            printer_type: this.printer_id.printer_type,
            print_engine_key,
        });

        try {
            console.log('[openCashbox] Sending RPC request to create print.job...');
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
                }],
                kwargs: {},
            });

            console.log('[openCashbox] RPC request successful. Result:', result);
            return { result, printerErrorCode: false };
        } catch (err) {
            console.error('[openCashbox] Open cashbox failed. Error:', err);
            console.error('[openCashbox] Error message:', err.message);
            return { result: false, printerErrorCode: err.message };
        }
    }

    async sendPrintingJob(img) {
        if (!this.printer_id) {
            return false
        }
        var open_cashdrawer = false;
        open_cashdrawer = this.is_open_cashbox_receipt_print;
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
                }],
                kwargs: {},
            });
            return { result, printerErrorCode: false };
        } catch (err) {
            console.error("Print job failed:", err);
            return { result: false, printerErrorCode: err.message };
        }
    }
}
