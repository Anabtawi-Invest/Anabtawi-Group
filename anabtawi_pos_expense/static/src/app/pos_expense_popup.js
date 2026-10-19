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
    // ``expense``: a refused expense (from get_pos_refused_expenses) to edit and resend.
    static props = ["close", "expense?", "onDone?"];

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        this.printer = useService("printer");
        const expense = this.props.expense;
        this.state = useState({
            loading: true,
            limit: 0,
            available: 0,
            types: [],
            typeId: expense ? String(expense.type_id) : "",
            amount: expense ? String(expense.amount) : "",
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

    get isEdit() {
        return Boolean(this.props.expense);
    }

    get dialogTitle() {
        return this.isEdit ? _t("Edit & Resend %s", this.props.expense.name) : _t("Expense");
    }

    get labels() {
        return {
            refuseReason: _t("Refuse reason:"),
            limit: _t("Limit"),
            available: _t("Available"),
            expenseType: _t("Expense Type"),
            selectType: _t("Select an expense type..."),
            noTypes: _t("No expense types are configured for this POS."),
            amount: _t("Amount"),
            exceeds: _t(
                "The amount exceeds the available balance (maximum %s).",
                this.format(this.maxAmount)
            ),
            cashOutDiff: _t("A Cash Out of %s will be made.", this.format(this.amountDifference)),
            cashInDiff: _t("A Cash In of %s will be made.", this.format(-this.amountDifference)),
            receiptPhoto: _t("Receipt Photo"),
            scanToUpload: _t("Scan to upload"),
            newPhoto: _t("New photo"),
            uploadExpired: _t("The upload link expired. Close and open the popup again."),
            currentPhotoHint: _t("Current photo. Scan the QR to replace it (optional)."),
            waitingPhoto: _t("Waiting for the photo..."),
            resend: _t("Resend for Approval"),
            confirm: _t("Confirm"),
            discard: _t("Discard"),
        };
    }

    get maxAmount() {
        // A refused expense is still counted in the balance, so its own amount is available again.
        return this.state.available + (this.props.expense?.amount || 0);
    }

    get exceedsAvailable() {
        return this.amountValue > this.maxAmount + 1e-9;
    }

    get amountDifference() {
        return this.isEdit ? this.amountValue - this.props.expense.amount : 0;
    }

    get hasNewPhoto() {
        return Boolean(this.state.upload?.has_image);
    }

    get isValid() {
        return (
            !this.state.loading &&
            this.state.typeId &&
            this.amountValue > 0 &&
            !this.exceedsAvailable &&
            (this.isEdit || this.hasNewPhoto)
        );
    }

    async confirm() {
        if (!this.isValid) {
            return;
        }
        if (this.isEdit) {
            return this.resend();
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

    async resend() {
        let result;
        try {
            result = await this.pos.data.call("pos.session", "resubmit_pos_expense", [
                this.sessionIds,
                this.props.expense.id,
                parseInt(this.state.typeId),
                this.amountValue,
                this.hasNewPhoto ? this.state.upload.token : false,
                ...getPosExpenseCashierArgs(this.pos),
            ]);
        } catch (error) {
            this.notification.add(error?.data?.message || _t("Could not resend the expense."), {
                type: "danger",
            });
            return;
        }
        this._stopPoll();
        const names = { name: result.name, original: result.original_name };
        let message = _t("%(original)s resent for approval as %(name)s.", names);
        if (result.reason) {
            const type = result.difference > 0 ? "out" : "in";
            const formattedDiff = this.format(Math.abs(result.difference));
            await printPosExpenseReceipt(this.pos, this.printer, {
                reason: result.reason,
                formattedAmount: formattedDiff,
                type,
            });
            message =
                type === "out"
                    ? _t("%(original)s resent for approval as %(name)s. Cash out of %(amount)s done.", {
                          ...names,
                          amount: formattedDiff,
                      })
                    : _t("%(original)s resent for approval as %(name)s. Cash in of %(amount)s done.", {
                          ...names,
                          amount: formattedDiff,
                      });
        }
        this.props.close();
        this.props.onDone?.();
        this.notification.add(message, { type: "success" });
    }
}
