/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class PredefinedDiscountAuthPopup extends Component {
    static template = "pos_predefined_discounts.PredefinedDiscountAuthPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        discounts: { type: Array, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Select Discount"),
        discounts: [],
    };

    setup() {
        this.state = useState({
            discountId: this.props.discounts?.[0]?.id || null,
        });
    }

    get canConfirm() {
        return Boolean(this.state.discountId);
    }

    confirm() {
        if (!this.canConfirm) {
            return;
        }
        this.props.getPayload({
            discountId: this.state.discountId,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
