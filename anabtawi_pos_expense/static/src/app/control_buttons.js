import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { PosExpensePopup } from "./pos_expense_popup";
import { RefusedExpensesPopup } from "./refused_expenses_popup";

patch(ControlButtons.prototype, {
    get showPosExpenseButton() {
        return this.pos.config.expense_limit > 0;
    },

    onClickPosExpense() {
        this.dialog.add(PosExpensePopup);
    },

    onClickRefusedExpenses() {
        this.dialog.add(RefusedExpensesPopup);
    },
});
