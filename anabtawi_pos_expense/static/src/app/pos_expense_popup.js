import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useAsyncLockedMethod } from "@point_of_sale/app/hooks/hooks";
import { getPosExpenseCashierArgs, printPosExpenseReceipt } from "./utils";

export class PosExpensePopup extends Component {
    static template = "anabtawi_pos_expense.PosExpensePopup";
    static components = { Dialog };
    static props = ["close"];

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        this.printer = useService("printer");
        this.state = useState({
            loading: true,
            limit: 0,
            available: 0,
            types: [],
            typeId: "",
            amount: "",
            upload: null,
        });
        this.confirm = useAsyncLockedMethod(this.confirm);
        this._poll = null;
        onMounted(() => this._load());
        onWillUnmount(() => this._stopPoll());
    }

    get sessionIds() {
        return [this.pos.session.id];
    }

    async _load() {
        try {
            const [data, upload] = await Promise.all([
                this.pos.data.call("pos.session", "get_pos_expense_data", [this.sessionIds]),
                this.pos.data.call("pos.session", "create_pos_expense_upload", [this.sessionIds]),
            ]);
            Object.assign(this.state, {
                limit: data.limit,
                available: data.available,
                types: data.types,
                upload,
            });
            this._poll = setInterval(() => this._refreshUpload(), 3000);
        } catch (error) {
            this.notification.add(error?.data?.message || _t("Could not load expense data."), {
                type: "danger",
            });
            this.props.close();
        } finally {
            this.state.loading = false;
        }
    }

    _stopPoll() {
        if (this._poll) {
            clearInterval(this._poll);
            this._poll = null;
        }
    }

    async _refreshUpload() {
        const token = this.state.upload?.token;
        if (!token) {
            return;
        }
        try {
            const status = await this.pos.data.call("pos.session", "get_pos_expense_upload_status", [
                this.sessionIds,
                token,
            ]);
            Object.assign(this.state.upload, status);
            if (!status.is_valid) {
                this._stopPoll();
            }
        } catch {
            // Keep the popup usable if one poll fails (e.g. short network loss).
        }
    }

    format(value) {
        return this.env.utils.formatCurrency(value || 0);
    }

    get amountValue() {
        const value = Number(String(this.state.amount).replace(",", "."));
        return Number.isFinite(value) ? value : 0;
    }

    get exceedsAvailable() {
        return this.amountValue > this.state.available + 1e-9;
    }

    get isValid() {
        return (
            !this.state.loading &&
            this.state.typeId &&
            this.amountValue > 0 &&
            !this.exceedsAvailable &&
            this.state.upload?.has_image
        );
    }

    async confirm() {
        if (!this.isValid) {
            return;
        }
        let result;
        try {
            result = await this.pos.data.call("pos.session", "create_pos_expense", [
                this.sessionIds,
                parseInt(this.state.typeId),
                this.amountValue,
                this.state.upload.token,
                ...getPosExpenseCashierArgs(this.pos),
            ]);
        } catch (error) {
            this.notification.add(error?.data?.message || _t("Could not save the expense."), {
                type: "danger",
            });
            return;
        }
        this._stopPoll();
        const formattedAmount = this.format(result.amount);
        await printPosExpenseReceipt(this.pos, this.printer, {
            reason: result.reason,
            formattedAmount,
            type: "out",
        });
        this.props.close();
        this.notification.add(
            _t("Expense %(name)s saved. Cash out of %(amount)s done.", {
                name: result.name,
                amount: formattedAmount,
            }),
            { type: "success" }
        );
    }
}
