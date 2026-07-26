/** @odoo-module **/

import { Component, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { CakePayLaterReceipt } from "./cake_pay_later_receipt";

export class CakePayLaterReceiptPopup extends Component {
    static template = "pos_custom_cake.CakePayLaterReceiptPopup";
    static components = { Dialog, CakePayLaterReceipt };
    static props = {
        close: Function,
        receipt: Object,
        printOptions: { type: Object, optional: true },
        autoPrint: { type: Boolean, optional: true },
    };

    setup() {
        this.printer = useService("printer");
        this.notification = useService("notification");
        onMounted(async () => {
            if (this.props.autoPrint) {
                await this.print();
            }
        });
    }

    get title() {
        return _t("Cake Order Receipt");
    }

    get labels() {
        return {
            print: _t("Print"),
            close: _t("Close"),
        };
    }

    async print() {
        try {
            const printResult = await this.printer.print(
                CakePayLaterReceipt,
                { receipt: this.props.receipt },
                this.props.printOptions || { webPrintFallback: true }
            );
            if (!printResult) {
                this.notification.add(
                    _t("No receipt printer found. Use your browser print dialog or connect a printer."),
                    { type: "warning" }
                );
            }
        } catch (error) {
            const message =
                error?.body || error?.message || _t("Receipt printing failed.");
            this.notification.add(message, { type: "warning" });
        }
    }

    close() {
        this.props.close();
    }
}
