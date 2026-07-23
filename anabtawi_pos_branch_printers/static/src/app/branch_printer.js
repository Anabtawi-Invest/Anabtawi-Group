/** @odoo-module */

import { BasePrinter } from "@point_of_sale/app/utils/printer/base_printer";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";

export class BranchPrinter extends BasePrinter {
    setup({ printer_id, pos_config_id }) {
        super.setup(...arguments);
        this.printer_id = printer_id;
        this.pos_config_id = pos_config_id;
    }

    /**
     * @override
     */
    async openCashbox() {
        try {
            const res = await rpc('/web/dataset/call_kw', {
                model: 'pos.branch.printer',
                method: 'send_print_job',
                args: [this.pos_config_id],
                kwargs: {
                    image_data: false,
                    is_open_cashbox: true,
                },
            });
            return { result: res ? res.result : false, printerErrorCode: (res && res.error) ? res.error : false };
        } catch (err) {
            console.error('[BranchPrinter] Cashbox failed:', err);
            return { result: false, printerErrorCode: err.message };
        }
    }

    /**
     * @override
     */
    async sendPrintingJob(img) {
        let open_cashdrawer = false;
        if (this.is_open_cashbox_receipt_print) {
            open_cashdrawer = true;
            this.is_open_cashbox_receipt_print = false;
        }

        try {
            const res = await rpc('/web/dataset/call_kw', {
                model: 'pos.branch.printer',
                method: 'send_print_job',
                args: [this.pos_config_id],
                kwargs: {
                    image_data: img,
                    is_open_cashbox: open_cashdrawer,
                },
            });
            return { result: res ? res.result : false, printerErrorCode: (res && res.error) ? res.error : false };
        } catch (err) {
            console.error('[BranchPrinter] Print job failed:', err);
            return { result: false, printerErrorCode: err.message };
        }
    }
}

patch(PosStore.prototype, {
    afterProcessServerData() {
        const res = super.afterProcessServerData(...arguments);
        const initBranchPrinter = () => {
            if (this.config.branch_printer_id) {
                const printerId = Array.isArray(this.config.branch_printer_id) 
                    ? this.config.branch_printer_id[0] 
                    : this.config.branch_printer_id;
                this.hardwareProxy.printer = new BranchPrinter({
                    printer_id: printerId,
                    pos_config_id: this.config.id,
                });
            }
        };

        if (res && typeof res.then === 'function') {
            return res.then(initBranchPrinter);
        } else {
            initBranchPrinter();
            return res;
        }
    },

    createPrinter(config) {
        if (this.config.branch_printer_id) {
            const printerId = Array.isArray(this.config.branch_printer_id) 
                ? this.config.branch_printer_id[0] 
                : this.config.branch_printer_id;
            return new BranchPrinter({
                printer_id: printerId,
                pos_config_id: this.config.id,
            });
        }
        return super.createPrinter(...arguments);
    }
});
