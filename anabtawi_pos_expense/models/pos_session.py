import base64

from markupsafe import Markup

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

    def _format_pos_expense_amount(self, amount):
        return formatLang(self.env, amount, currency_obj=self.currency_id)

    def _get_pos_expense_type(self, type_id):
        ExpenseType = self.env["pos.expense.type"]
        expense_type = ExpenseType.search(
            ExpenseType._get_domain_for_config(self.config_id) + [("id", "=", int(type_id or 0))],
            limit=1,
        )
        if not expense_type:
            raise UserError(_("Please select a valid expense type."))
        return expense_type

    def _check_pos_expense_amount(self, amount, increase):
        """Round ``amount`` and make sure ``increase`` (the extra cash leaving the drawer) fits the balance."""
        currency = self.currency_id
        amount = currency.round(float(amount or 0.0))
        if currency.compare_amounts(amount, 0.0) <= 0:
            raise UserError(_("The expense amount must be greater than zero."))
        available = self.config_id.expense_available_amount
        if currency.compare_amounts(increase(amount), available) > 0:
            max_amount = available + amount - increase(amount)
            raise UserError(_(
                "The amount exceeds the available expense balance (maximum %(max)s).",
                max=self._format_pos_expense_amount(max_amount),
            ))
        return amount

    def _get_pos_refused_expense(self, expense_id):
        expense = self.env["pos.expense"].sudo().browse(int(expense_id or 0)).exists()
        if not expense or expense.config_id != self.config_id:
            raise UserError(_("This expense does not belong to this Point of Sale."))
        if expense.state != "refused":
            raise UserError(_("Expense %s is not refused anymore. Please reload the list.", expense.name))
        return expense

    def _create_pos_expense_cash_move(self, sign, amount, reason, employee_id=False):
        self.ensure_one()
        extras = {
            "translatedType": _("in") if sign > 0 else _("out"),
            "formattedAmount": self._format_pos_expense_amount(amount),
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
        self._lock_pos_expense_config()
        expense_type = self._get_pos_expense_type(type_id)
        amount = self._check_pos_expense_amount(amount, lambda new_amount: new_amount)

        upload = self._get_pos_expense_upload(token)
        if not upload.image:
            raise UserError(_("Please upload the receipt photo first."))

        expense = self.env["pos.expense"].sudo().create({
            "config_id": self.config_id.id,
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
            "available": self.config_id.expense_available_amount,
        }

    def get_pos_refused_expenses(self):
        self.ensure_one()
        return self.config_id._get_unreturned_refused_expenses()._prepare_pos_refused_data()

    def return_pos_expense(self, expense_id, cashier_name=False, employee_id=False):
        self.ensure_one()
        self._check_pos_expense_session()
        self._lock_pos_expense_config()
        expense = self._get_pos_refused_expense(expense_id)

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

    def resubmit_pos_expense(self, expense_id, type_id, amount, token=False, cashier_name=False, employee_id=False):
        self.ensure_one()
        self._check_pos_expense_session()
        self._lock_pos_expense_config()
        expense = self._get_pos_refused_expense(expense_id)
        currency = self.currency_id
        old_amount = expense.amount
        old_type = expense.type_id

        expense_type = self._get_pos_expense_type(type_id)
        # The refused amount is still counted in the balance, so only an increase needs room.
        amount = self._check_pos_expense_amount(amount, lambda new_amount: new_amount - old_amount)

        upload = self._get_pos_expense_upload(token) if token else self.env["pos.expense.upload"]
        new_image = upload.image if upload else False

        difference = currency.round(amount - old_amount)
        cash_move = self.env["account.bank.statement.line"]
        reason = False
        if not currency.is_zero(difference):
            reason = _("%(name)s - Adjustment - %(type)s", name=expense.name, type=expense_type.name)
            sign = -1 if difference > 0 else 1
            cash_move = self._create_pos_expense_cash_move(sign, abs(difference), reason, employee_id)

        cashier = cashier_name or self.env.user.name
        changes = [_("Previous refuse reason: %s", expense.refuse_reason or "-")]
        if expense_type != old_type:
            changes.append(_("Type: %(old)s → %(new)s", old=old_type.name, new=expense_type.name))
        if not currency.is_zero(difference):
            changes.append(_(
                "Amount: %(old)s → %(new)s (Cash %(direction)s of %(diff)s in %(session)s)",
                old=self._format_pos_expense_amount(old_amount),
                new=self._format_pos_expense_amount(amount),
                direction=_("out") if difference > 0 else _("in"),
                diff=self._format_pos_expense_amount(abs(difference)),
                session=self.name,
            ))
        attachments = []
        if new_image:
            changes.append(_("New receipt photo uploaded (previous photo attached)."))
            if expense.image:
                attachments.append((f"{expense.name}-previous-photo.png", base64.b64decode(expense.image)))
        body = Markup("<p>%s</p><ul>%s</ul>") % (
            _("Resubmitted from the POS by %s", cashier),
            Markup("").join(Markup("<li>%s</li>") % change for change in changes),
        )
        expense.message_post(body=body, attachments=attachments)

        vals = {
            "state": "to_approve",
            "type_id": expense_type.id,
            "amount": amount,
            "refuse_reason": False,
            "decided_by_id": False,
            "decision_date": False,
            "resubmit_count": expense.resubmit_count + 1,
        }
        if new_image:
            vals["image"] = new_image
        if cash_move:
            vals["adjustment_statement_line_ids"] = [fields.Command.link(cash_move.id)]
        expense.write(vals)
        if upload:
            upload.sudo().unlink()

        expense._invalidate_config_balance()
        return {
            "name": expense.name,
            "amount": amount,
            "difference": difference,
            "reason": reason,
            "available": self.config_id.expense_available_amount,
        }
