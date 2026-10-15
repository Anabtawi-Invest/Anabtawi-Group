import { CashMovePopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_popup";
import { patch } from "@web/core/utils/patch";

patch(CashMovePopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.reasonId = false;
    },

    get availableCashMoveReasons() {
        const type = this.state.type;
        return this.pos.models["pos.cash.move.reason"]
            .readAll()
            .filter((reason) => reason.move_type === "both" || reason.move_type === type)
            .sort((a, b) => a.sequence - b.sequence || a.id - b.id);
    },

    onSelectCashMoveReason(value) {
        const reasonId = parseInt(value);
        const reason = this.availableCashMoveReasons.find((r) => r.id === reasonId);
        this.state.reasonId = reason ? reason.id : false;
        this.state.reason = reason ? reason.name : "";
    },

    onClickButton(type) {
        if (this.state.type !== type) {
            this.state.reasonId = false;
            this.state.reason = "";
        }
        return super.onClickButton(type);
    },
});
