/** @odoo-module **/

import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class MepIdPopup extends Component {
    static template = "pos_mep_id.MepIdPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        placeholder: { type: String, optional: true },
        confirmLabel: { type: String, optional: true },
        cancelLabel: { type: String, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Enter MEPs ID"),
        placeholder: _t("MEP ID"),
        confirmLabel: _t("Confirm"),
        cancelLabel: _t("Cancel"),
    };

    setup() {
        this.state = useState({ mepId: "" });
        this.inputRef = useRef("mep_id_input");
        onMounted(() => {
            this.inputRef.el?.focus();
        });
    }

    get canConfirm() {
        return Boolean(this.state.mepId.trim());
    }

    confirm() {
        if (!this.canConfirm) {
            return;
        }
        this.props.getPayload(this.state.mepId.trim());
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
