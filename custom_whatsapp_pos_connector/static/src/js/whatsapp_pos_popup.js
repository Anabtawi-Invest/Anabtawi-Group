/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class WhatsAppPosOrderPopup extends Component {
    static template = "custom_whatsapp_pos_connector.WhatsAppPosOrderPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        order: Object,
        onLoad: Function,
    };

    async loadOrder() {
        await this.props.onLoad(this.props.order);
        this.props.close();
    }

    closePopup() {
        this.props.close();
    }

    get title() {
        return _t("New WhatsApp Order");
    }

    get lines() {
        return this.props.order?.line_ids || [];
    }
}
