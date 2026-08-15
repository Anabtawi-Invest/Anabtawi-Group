/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { user } from "@web/core/user";
import { onMounted, useState } from "@odoo/owl";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { getOrCreateCloseDeviceToken } from "@pos_close_ip_restrict/app/close_device_token";

patch(Navbar.prototype, {
    setup() {
        super.setup(...arguments);
        this.closeDeviceState = useState({ canRegister: false });
        onMounted(async () => {
            this.closeDeviceState.canRegister = await user.hasGroup(
                "point_of_sale.group_pos_manager"
            );
        });
    },
    get canRegisterCloseDevice() {
        return this.closeDeviceState.canRegister;
    },
    async registerCloseDevice() {
        const token = getOrCreateCloseDeviceToken();
        try {
            const result = await this.pos.data.call("pos.config", "register_close_device", [
                this.pos.config.id,
                token,
                this.pos.config.name,
            ]);
            const alreadyAllowed = result && result.created === false;
            this.dialog.add(AlertDialog, {
                title: _t("Close Register Device"),
                body: alreadyAllowed
                    ? _t("This device is already allowed to close the register.")
                    : _t("This device can now close the register."),
            });
        } catch {
            this.dialog.add(AlertDialog, {
                title: _t("Close Register Device"),
                body: _t("You cannot allow this device to close the register."),
            });
        }
    },
});
