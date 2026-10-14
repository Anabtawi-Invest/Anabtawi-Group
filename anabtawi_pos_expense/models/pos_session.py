from odoo import _, models
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
        if self.state != "opened":
            raise UserError(_("The POS session must be open to register an expense."))
        if not self.cash_journal_id:
            raise UserError(_("There is no cash payment method for this POS session."))

        config = self.config_id
        currency = config.currency_id
        # Serialize expenses of the same POS so two cashiers cannot exceed the limit together.
        self.env.cr.execute(SQL("SELECT id FROM pos_config WHERE id = %s FOR UPDATE", config.id))
        config.invalidate_recordset(["expense_pending_amount", "expense_available_amount"])

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
        extras = {
            "translatedType": _("out"),
            "formattedAmount": formatLang(self.env, amount, currency_obj=currency),
        }
        if employee_id:
            extras["employee_id"] = int(employee_id)
        statement_vals = self._prepare_account_bank_statement_line_vals(
            self, -1, amount, reason, self.env.user.partner_id.id, extras
        )
        expense.statement_line_id = self.env["account.bank.statement.line"].sudo().with_context(
            no_retrieve_partner=True
        ).create(statement_vals)
        upload.sudo().unlink()

        config.invalidate_recordset(["expense_pending_amount", "expense_available_amount"])
        return {
            "name": expense.name,
            "reason": reason,
            "amount": amount,
            "available": config.expense_available_amount,
        }
