/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

export class AdvanceDetailsPopup extends Component {
    static template = "pos_advance.AdvanceDetailsPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        confirm: Function,
    };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            dueDate: this._getDefaultDueDate(),
            pickupPosId: this.pos.config.id, // Default to current POS
            availablePos: [],
        });

        this._loadAvailablePos();
    }

    _getDefaultDueDate() {
        // Default due date: 7 days from now
        const date = new Date();
        date.setDate(date.getDate() + 7);
        return date.toISOString().split('T')[0]; // Format: YYYY-MM-DD
    }

    async _loadAvailablePos() {
        try {
            const posConfigs = await this.orm.searchRead(
                "pos.config",
                [],
                ["id", "name"],
                { order: "name" }
            );
            this.state.availablePos = posConfigs;
        } catch (error) {
            console.error("[ADVANCE] Error loading POS configs:", error);
            this.notification.add(
                _t("Error loading available POS locations"),
                { type: "danger" }
            );
        }
    }

    onDueDateChange(ev) {
        this.state.dueDate = ev.target.value;
    }

    onPickupPosChange(ev) {
        this.state.pickupPosId = parseInt(ev.target.value);
    }

    onConfirm() {
        if (!this.state.dueDate) {
            this.notification.add(
                _t("Please select a due date"),
                { type: "warning" }
            );
            return;
        }

        if (!this.state.pickupPosId) {
            this.notification.add(
                _t("Please select a pickup location"),
                { type: "warning" }
            );
            return;
        }

        this.props.confirm({
            due_date: this.state.dueDate,
            pickup_pos_id: this.state.pickupPosId,
        });
        this.props.close();
    }

    onCancel() {
        this.props.close();
    }
}
