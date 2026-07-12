/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class MepsWaitingPopup extends Component {
    static template = "pos_mep_id.MepsWaitingPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        body: { type: String, optional: true },
        close: Function,
    };
    static defaultProps = {
        title: _t("MEPS Terminal"),
        body: _t("Please follow the instructions on the payment terminal..."),
    };
}
