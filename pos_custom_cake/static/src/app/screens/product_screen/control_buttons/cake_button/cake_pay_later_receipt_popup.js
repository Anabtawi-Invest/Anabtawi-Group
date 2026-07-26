/** @odoo-module **/

import { Component, useRef } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { CakePayLaterReceipt } from "./cake_pay_later_receipt";

const RECEIPT_PRINT_STYLES = `
    body { margin: 0; padding: 12px; font-family: sans-serif; color: #000; background: #fff; }
    .pos-receipt { max-width: 320px; margin: 0 auto; font-size: 14px; line-height: 1.4; }
    .fw-bolder { font-weight: 700; }
    .fs-5 { font-size: 1.1rem; }
    .text-center { text-align: center; }
    .text-end { text-align: right; }
    .text-muted { color: #666; }
    .small { font-size: 12px; }
    .d-flex { display: flex; }
    .w-75 { width: 75%; }
    .w-25 { width: 25%; }
    .ms-auto { margin-left: auto; }
    .pt-1 { padding-top: 0.25rem; }
    .pt-3 { padding-top: 0.75rem; }
    .mt-2 { margin-top: 0.5rem; }
    .p-2 { padding: 0.5rem; }
    .border-top { border-top: 1px solid #ccc; }
`;

export class CakePayLaterReceiptPopup extends Component {
    static template = "pos_custom_cake.CakePayLaterReceiptPopup";
    static components = { Dialog, CakePayLaterReceipt };
    static props = {
        close: Function,
        receipt: Object,
    };

    setup() {
        this.receiptRef = useRef("receipt");
        this.notification = useService("notification");
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

    print() {
        const receiptNode = this.receiptRef.el;
        if (!receiptNode) {
            this.notification.add(_t("Receipt not ready."), { type: "warning" });
            return;
        }
        try {
            this._printInBrowser(receiptNode);
        } catch (error) {
            this.notification.add(
                error?.message || _t("Could not open the print dialog."),
                { type: "warning" }
            );
        }
    }

    /**
     * Must run synchronously from the click handler so the browser keeps the
     * user-gesture required to open the print dialog.
     */
    _printInBrowser(receiptNode) {
        const iframe = document.createElement("iframe");
        iframe.setAttribute(
            "style",
            "position:fixed;right:0;bottom:0;width:0;height:0;border:0;"
        );
        document.body.appendChild(iframe);

        const printWindow = iframe.contentWindow;
        const doc = printWindow.document;
        doc.open();
        doc.write(
            `<!DOCTYPE html><html><head><title>${_t("Cake Order Receipt")}</title>` +
                `<style>${RECEIPT_PRINT_STYLES}</style></head><body>` +
                `${receiptNode.innerHTML}</body></html>`
        );
        doc.close();

        printWindow.focus();
        printWindow.print();

        setTimeout(() => {
            iframe.remove();
        }, 2000);
    }

    close() {
        this.props.close();
    }
}
