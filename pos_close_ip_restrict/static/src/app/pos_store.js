/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async closeSession() {
        const result = await this.data.call("pos.session", "check_close_allowed_ip", [
            this.session.id,
        ]);
        if (result && result.allowed === false) {
            this.dialog.add(AlertDialog, {
                title: _t("Close Register Restricted"),
                body:
                    result.message ||
                    _t("You cannot close this register from this device."),
            });
            return;
        }
        return super.closeSession(...arguments);
    },
});
