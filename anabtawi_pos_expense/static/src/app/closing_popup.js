import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    async handleClosingError(response) {
        // The core dialog offers "Cancel Orders", which would delete draft orders; refused
        // expenses need a plain message instead.
        if (response?.pos_expense_refused) {
            this.dialog.add(AlertDialog, {
                title: response.title,
                body: response.message,
            });
            return;
        }
        return super.handleClosingError(...arguments);
    },
});
