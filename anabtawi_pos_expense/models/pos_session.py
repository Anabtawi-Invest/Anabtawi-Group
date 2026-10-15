from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL
from odoo.tools.misc import formatLang


class PosSession(models.Model):
    _inherit = "pos.session"

    def _get_pos_expense_upload(self, token):
        self.ensure_one()
        upload = self.env["pos.expense.upload"].get_by_token(token)
        if not upload or upload.session_id != self:
            raise UserError(_("The receipt photo upload was not found. Please close the popup and try again."))
        return upload

    def _check_pos_expense_session(self):
        self.ensure_one()
        if self.state != "opened":
            raise UserError(_("The POS session must be open to register an expense."))
        if not self.cash_journal_id:
            raise UserError(_("There is no cash payment method for this POS session."))

    def _lock_pos_expense_config(self):
        # Serialize expense operations of the same POS so concurrent cashiers stay within the limit.
        self.env.cr.execute(SQL("SELECT id FROM pos_config WHERE id = %s FOR UPDATE", self.config_id.id))
        self.config_id.invalidate_recordset(["expense_pending_amount", "expense_available_amount"])

    def _create_pos_expense_cash_move(self, sign, amount, reason, employee_id=False):
        self.ensure_one()
        extras = {
            "translatedType": _("in") if sign > 0 else _("out"),
            "formattedAmount": formatLang(self.env, amount, currency_obj=self.currency_id),
        }
        if employee_id:
            extras["employee_id"] = int(employee_id)
        statement_vals = self._prepare_account_bank_statement_line_vals(
            self, sign, amount, reason, self.env.user.partner_id.id, extras
        )
        return self.env["account.bank.statement.line"].sudo().with_context(
            no_retrieve_partner=True
        ).create(statement_vals)

    def get_pos_expense_data(self):
        self.ensure_one()
        config = self.config_id
        types = self.env["pos.expense.type"].search(self.env["pos.expense.type"]._get_domain_for_config(config))
        return {
            "limit": config.expense_limit,
            "pending": config.expense_pending_amount,
            "available": config.expense_available_amount,
            "types": [{"id": t.id, "name": t.name} for t in types],
        }

    def create_pos_expense_upload(self):
        self.ensure_one()
        upload = self.env["pos.expense.upload"].sudo().create({"session_id": self.id})
        return upload._prepare_pos_data()

    def get_pos_expense_upload_status(self, token):
        return self._get_pos_expense_upload(token)._prepare_status_data()

    def create_pos_expense(self, type_id, amount, token, cashier_name=False, employee_id=False):
        self.ensure_one()
        self._check_pos_expense_session()
        config = self.config_id
        currency = config.currency_id
        self._lock_pos_expense_config()

        expense_type = self.env["pos.expense.type"].search(
            self.env["pos.expense.type"]._get_domain_for_config(config) + [("id", "=", int(type_id or 0))],
            limit=1,
        )
        if not expense_type:
            raise UserError(_("Please select a valid expense type."))

        amount = currency.round(float(amount or 0.0))
        if currency.compare_amounts(amount, 0.0) <= 0:
            raise UserError(_("The expense amount must be greater than zero."))
        available = config.expense_available_amount
        if currency.compare_amounts(amount, available) > 0:
            raise UserError(_(
                "The amount exceeds the available expense balance (%(available)s).",
                available=formatLang(self.env, available, currency_obj=currency),
            ))

        upload = self._get_pos_expense_upload(token)
        if not upload.image:
            raise UserError(_("Please upload the receipt photo first."))

        expense = self.env["pos.expense"].sudo().create({
            "config_id": config.id,
            "session_id": self.id,
            "type_id": expense_type.id,
            "amount": amount,
            "cashier_name": cashier_name or self.env.user.name,
            "image": upload.image,
        })
        reason = f"{expense.name} - {expense_type.name}"
        expense.statement_line_id = self._create_pos_expense_cash_move(-1, amount, reason, employee_id)
        upload.sudo().unlink()

        expense._invalidate_config_balance()
        return {
            "name": expense.name,
            "reason": reason,
            "amount": amount,
            "available": config.expense_available_amount,
        }

    def get_pos_refused_expenses(self):
        self.ensure_one()
        return self.config_id._get_unreturned_refused_expenses()._prepare_pos_refused_data()

    def return_pos_expense(self, expense_id, cashier_name=False, employee_id=False):
        self.ensure_one()
        self._check_pos_expense_session()
        self._lock_pos_expense_config()
        expense = self.env["pos.expense"].sudo().browse(int(expense_id or 0)).exists()
        if not expense or expense.config_id != self.config_id:
            raise UserError(_("This expense does not belong to this Point of Sale."))
        if expense.state != "refused":
            raise UserError(_("Expense %s is not waiting for a return.", expense.name))

        reason = _("%(name)s - Return - %(type)s", name=expense.name, type=expense.type_id.name)
        cash_in = self._create_pos_expense_cash_move(1, expense.amount, reason, employee_id)
        expense.write({
            "state": "returned",
            "return_session_id": self.id,
            "return_cashier_name": cashier_name or self.env.user.name,
            "return_date": fields.Datetime.now(),
            "return_statement_line_id": cash_in.id,
        })
        expense._invalidate_config_balance()
        return {
            "name": expense.name,
            "reason": reason,
            "amount": expense.amount,
        }

    def _get_pos_expense_close_block_message(self):
        self.ensure_one()
        if self.rescue:
            return False
        refused = self.config_id._get_unreturned_refused_expenses()
        if not refused:
            return False
        lines = "\n".join(
            f"- {expense.name} ({expense.type_id.name}): "
            f"{formatLang(self.env, expense.amount, currency_obj=expense.currency_id)}"
            for expense in refused
        )
        return _(
            "You cannot close the session while there are refused expenses that were not returned.\n"
            "Use the 'Refused Expenses' button in the POS Actions menu to return them first:\n%s",
            lines,
        )

    def _cannot_close_session(self, bank_payment_method_diffs=None):
        result = super()._cannot_close_session(bank_payment_method_diffs)
        if result:
            return result
        message = self._get_pos_expense_close_block_message()
        if message:
            return {
                "successful": False,
                "type": "alert",
                "title": _("Refused expenses to return"),
                "message": message,
                "redirect": False,
                "pos_expense_refused": True,
            }
        return result

    def action_pos_session_closing_control(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        for session in self:
            message = session._get_pos_expense_close_block_message()
            if message:
                raise UserError(message)
        return super().action_pos_session_closing_control(balancing_account, amount_to_balance, bank_payment_method_diffs)
