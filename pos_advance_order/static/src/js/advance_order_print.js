/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { AdvanceOrderReceipt } from "../app/screens/product_screen/control_buttons/advance_order_button/advance_order_receipt";

const RECEIPT_PRINT_STYLES = `
.pos-receipt.advance-order-receipt{font-size:13px;line-height:1.35;max-width:80mm;margin:0 auto;padding:12px 10px}
.advance-order-receipt .advance-receipt-header{text-align:center;border-bottom:2px dashed #6f42c1;padding-bottom:10px;margin-bottom:10px}
.advance-order-receipt .advance-receipt-title{font-size:15px;font-weight:700;letter-spacing:.04em;color:#6f42c1;margin-top:4px}
.advance-order-receipt .advance-receipt-ref{display:inline-block;margin-top:6px;padding:2px 8px;border:1px solid #6f42c1;border-radius:4px;font-size:12px;font-weight:600}
.advance-order-receipt .advance-receipt-meta{border-bottom:1px dashed #ccc;padding-bottom:8px;margin-bottom:8px}
.advance-order-receipt .advance-receipt-meta-row{display:flex;justify-content:space-between;gap:8px;margin-bottom:2px}
.advance-order-receipt .advance-receipt-meta-row span:first-child{color:#555;flex-shrink:0}
.advance-order-receipt .advance-receipt-meta-row span:last-child{text-align:right;word-break:break-word}
.advance-order-receipt .advance-receipt-lines-header,.advance-order-receipt .advance-receipt-line{display:flex;gap:4px}
.advance-order-receipt .advance-receipt-lines-header{font-weight:700;border-bottom:1px solid #000;padding-bottom:4px;margin-bottom:4px}
.advance-order-receipt .advance-receipt-line{padding:3px 0;border-bottom:1px dotted #ddd}
.advance-order-receipt .advance-col-item{flex:1 1 50%;word-break:break-word}
.advance-order-receipt .advance-col-qty{flex:0 0 18%;text-align:center}
.advance-order-receipt .advance-col-price{flex:0 0 28%;text-align:right}
.advance-order-receipt .advance-receipt-summary{margin-top:10px;border:2px solid #333;border-radius:6px;overflow:hidden}
.advance-order-receipt .advance-summary-row{display:flex;justify-content:space-between;padding:5px 8px;border-bottom:1px solid #ddd}
.advance-order-receipt .advance-summary-row:last-child{border-bottom:none}
.advance-order-receipt .advance-receipt-title-completion{color:#198754}
.advance-order-receipt .advance-pledge-line{background-color:#fffdf5}
.advance-order-receipt .advance-pledge-row{background-color:#fff9e6;color:#856404;font-weight:600}
.advance-order-receipt .advance-receipt-note-success{background:#d4edda;border-color:#28a745;color:#155724}
.advance-order-receipt .advance-deposit-row{background-color:#f3efff}
.advance-order-receipt .advance-change-row{background-color:#d4edda;color:#155724;font-weight:600}
.advance-order-receipt .advance-remaining-row{background-color:#6f42c1;color:#fff;font-size:14px;font-weight:700;padding:8px}
.advance-order-receipt .advance-receipt-footer{text-align:center;margin-top:12px;padding-top:8px;border-top:1px dashed #ccc;font-size:12px;color:#666}
.advance-order-receipt .advance-receipt-note{margin-top:8px;padding:6px 8px;background:#fff3cd;border:1px solid #ffc107;border-radius:4px;font-size:11px;text-align:center;color:#856404}
.fw-bolder{font-weight:700}.fs-5{font-size:1.1rem}.text-muted{color:#6c757d}.text-danger{color:#dc3545}
@media print{body{margin:0;width:80mm}@page{margin:4mm}}
`;

function openBrowserPrintWindow(html, title) {
    const printWindow = window.open("", "_blank", "width=360,height=720");
    if (!printWindow) {
        return false;
    }
    printWindow.document.write(`<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <title>${title}</title>
    <style>${RECEIPT_PRINT_STYLES}</style>
</head>
<body onload="window.print(); setTimeout(function(){ window.close(); }, 250);">
    ${html}
</body>
</html>`);
    printWindow.document.close();
    return true;
}

export async function printAdvanceOrderReceiptInBrowser(renderer, receiptData, title = "Advance Order Receipt") {
    const el = await renderer.toHtml(AdvanceOrderReceipt, { receipt: receiptData });
    const opened = openBrowserPrintWindow(el.outerHTML, title);
    if (!opened) {
        throw new Error("POPUP_BLOCKED");
    }
}

/**
 * Print advance order receipt via POS printer when available, otherwise browser print.
 * Returns { printed: boolean, method: "pos" | "browser" | "none" }.
 */
export async function printAdvanceOrderReceipt({
    printer,
    renderer,
    receiptData,
    printOptions = {},
}) {
    const options = { webPrintFallback: true, ...printOptions };
    try {
        const result = await printer.print(AdvanceOrderReceipt, { receipt: receiptData }, options);
        if (result) {
            return { printed: true, method: "pos" };
        }
    } catch (error) {
        console.warn("[ADVANCE_ORDER] POS printer failed, using browser fallback.", error);
    }

    try {
        const title = receiptData.isCompletion
            ? _t("Advance Completion Receipt")
            : receiptData.isRefund
              ? _t("Advance Refund Receipt")
              : _t("Advance Order Receipt");
        await printAdvanceOrderReceiptInBrowser(renderer, receiptData, title);
        return { printed: true, method: "browser" };
    } catch (error) {
        console.error("[ADVANCE_ORDER] Browser print fallback failed.", error);
        if (error?.message === "POPUP_BLOCKED") {
            throw error;
        }
        return { printed: false, method: "none" };
    }
}
