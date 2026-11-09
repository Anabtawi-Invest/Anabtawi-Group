/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { _t } from "@web/core/l10n/translation";

const DIALOG_PATCHED = Symbol("posJofotaraBackgroundSend");

function lastLine(body) {
    const lines = String(body || "")
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
    return lines.length ? lines[lines.length - 1] : "";
}

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        // The standard Jordan module opens a long "receipt is stuck" dialog.
        // Replace that text once, without stacking wrappers on later orders.
        if (!this.dialog.add[DIALOG_PATCHED]) {
            const originalAdd = this.dialog.add.bind(this.dialog);
            const wrappedAdd = (component, props, options) => {
                if (props?.title === _t("JoFotara Error")) {
                    const error = lastLine(props.body);
                    props = {
                        ...props,
                        title: _t("JoFotara"),
                        body: error
                            ? _t(
                                  "تم حفظ عملية البيع. سيتم إرسال الفاتورة إلى جوفوتارا تلقائياً.\nThe sale is saved. JoFotara will retry in the background.\n\n%s",
                                  error
                              )
                            : _t(
                                  "تم حفظ عملية البيع. سيتم إرسال الفاتورة إلى جوفوتارا تلقائياً.\nThe sale is saved. JoFotara will retry in the background."
                              ),
                    };
                }
                return originalAdd(component, props, options);
            };
            wrappedAdd[DIALOG_PATCHED] = true;
            this.dialog.add = wrappedAdd;
        }
    },
});
