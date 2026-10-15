import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { formatCurrency } from "@web/core/currency";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this._notifyRefusedPosExpenses();
        return result;
    },

    async _notifyRefusedPosExpenses() {
        if (!(this.config.expense_limit > 0) || !this.session?.id) {
            return;
        }
        try {
            const expenses = await this.data.call("pos.session", "get_pos_refused_expenses", [
                [this.session.id],
            ]);
            if (!expenses.length) {
                return;
            }
            const total = expenses.reduce((sum, expense) => sum + expense.amount, 0);
            this.notification.add(
                _t(
                    "%(count)s refused expense(s) must be returned (%(total)s). Use Actions > Refused Expenses before closing the session.",
                    { count: expenses.length, total: formatCurrency(total, this.currency.id) }
                ),
                { type: "warning", sticky: true }
            );
        } catch {
            // A failed check at startup must not block the POS; closing is still guarded server-side.
        }
    },
});
