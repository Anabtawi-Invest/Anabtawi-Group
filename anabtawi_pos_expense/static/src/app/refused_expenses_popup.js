import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useAsyncLockedMethod } from "@point_of_sale/app/hooks/hooks";
import { formatDateTime, deserializeDateTime } from "@web/core/l10n/dates";
import { getPosExpenseCashierArgs, printPosExpenseReceipt } from "./utils";

export class RefusedExpensesPopup extends Component {
    static template = "anabtawi_pos_expense.RefusedExpensesPopup";
    static components = { Dialog };
    static props = ["close"];

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.printer = useService("printer");
        this.state = useState({ loading: true, expenses: [] });
        this.returnExpense = useAsyncLockedMethod(this.returnExpense);
        onMounted(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.expenses = await this.pos.data.call("pos.session", "get_pos_refused_expenses", [
                [this.pos.session.id],
            ]);
        } catch (error) {
            this.notification.add(error?.data?.message || _t("Could not load refused expenses."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    format(value) {
        return this.env.utils.formatCurrency(value || 0);
    }

    formatDate(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    get total() {
        return this.state.expenses.reduce((sum, expense) => sum + expense.amount, 0);
    }

    onClickReturn(expense) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Return expense %s", expense.name),
            body: _t(
                "Put %s back in the cash drawer? A Cash In will be registered in this session.",
                this.format(expense.amount)
            ),
            confirmLabel: _t("Return"),
            confirm: () => this.returnExpense(expense),
            cancel: () => {},
        });
    }

    async returnExpense(expense) {
        let result;
        try {
            result = await this.pos.data.call("pos.session", "return_pos_expense", [
                [this.pos.session.id],
                expense.id,
                ...getPosExpenseCashierArgs(this.pos),
            ]);
        } catch (error) {
            this.notification.add(error?.data?.message || _t("Could not return the expense."), {
                type: "danger",
            });
            await this.load();
            return;
        }
        const formattedAmount = this.format(result.amount);
        await printPosExpenseReceipt(this.pos, this.printer, {
            reason: result.reason,
            formattedAmount,
            type: "in",
        });
        this.notification.add(
            _t("Expense %(name)s returned. Cash in of %(amount)s done.", {
                name: result.name,
                amount: formattedAmount,
            }),
            { type: "success" }
        );
        await this.load();
    }
}
