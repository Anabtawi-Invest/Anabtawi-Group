/* @odoo-module */

import { BasePrinter } from "@point_of_sale/app/utils/printer/base_printer";
import { rpc } from "@web/core/network/rpc";

export class CrPrinter extends BasePrinter {
    setup({ printer_id }) {
        super.setup(...arguments);
        this.printer_id = printer_id;
        this.is_open_cashbox_receipt_print = false;
    }

    /**
     * @override
     */
    async openCashbox() {
        console.log('[CrPrinter:openCashbox] Called');

        if (!this.printer_id || typeof this.printer_id !== 'object') {
            console.error('[CrPrinter:openCashbox] printer_id is not a valid record:', this.printer_id);
            return { result: false, printerErrorCode: 'Invalid printer_id' };
        }

        const print_engine_key = this.printer_id.print_engine_key || '';
        if (!print_engine_key) {
            console.error('[CrPrinter:openCashbox] print_engine_key is MISSING for printer:',
                this.printer_id.name, '- Cash drawer job will NOT be routed correctly.');
        }

        console.log('[CrPrinter:openCashbox] Printer details:', {
            ip: this.printer_id.ip,
            port: this.printer_id.port,
            name: this.printer_id.name,
            printer_type: this.printer_id.printer_type,
            print_engine_key: print_engine_key ? '***' + print_engine_key.slice(-6) : 'NONE',
        });

        try {
            console.log('[CrPrinter:openCashbox] Sending RPC request to create print.job...');
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

            console.log('[CrPrinter:openCashbox] RPC request successful. Result:', result);
            return { result, printerErrorCode: false };
        } catch (err) {
            console.error('[CrPrinter:openCashbox] Open cashbox failed. Error:', err);
            console.error('[CrPrinter:openCashbox] Error message:', err.message);
            return { result: false, printerErrorCode: err.message };
        }
    }

    async sendPrintingJob(img) {
        if (!this.printer_id || typeof this.printer_id !== 'object') {
            console.error('[CrPrinter:sendPrintingJob] printer_id is not a valid record:', this.printer_id);
            return false;
        }

        const print_engine_key = this.printer_id.print_engine_key || '';
        if (!print_engine_key) {
            console.error('[CrPrinter:sendPrintingJob] print_engine_key is MISSING for printer:',
                this.printer_id.name, '- Print job will NOT be routed correctly.',
                'Check that the printer has a Print Engine Client with a valid key assigned.');
            return { result: false, printerErrorCode: 'Missing print_engine_key — print job cannot be routed.' };
        }

        var open_cashdrawer = false;
        open_cashdrawer = this.is_open_cashbox_receipt_print;
        if (open_cashdrawer) {
            this.is_open_cashbox_receipt_print = false;
        }

        try {
            console.log('[CrPrinter:sendPrintingJob] Sending to printer:', this.printer_id.name,
                '| Key:', '***' + print_engine_key.slice(-6),
                '| Cashbox:', open_cashdrawer);

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
            console.error("[CrPrinter:sendPrintingJob] Print job failed:", err);
            return { result: false, printerErrorCode: err.message };
        }
    }
}
