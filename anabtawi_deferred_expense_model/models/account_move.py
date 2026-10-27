# -*- coding: utf-8 -*-
from itertools import chain

from dateutil.relativedelta import relativedelta

from odoo import Command, _, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    deferred_expense_model_id = fields.Many2one(
        "deferred.expense.model",
        string="Deferred Expense Model",
        index=True,
        copy=False,
        help="Set on deferral journal entries generated from a deferred expense model.",
    )

    def action_open_deferred_expense_model(self):
        self.ensure_one()
        if not self.deferred_expense_model_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": self.deferred_expense_model_id.display_name,
            "res_model": "deferred.expense.model",
            "res_id": self.deferred_expense_model_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _prepare_deferred_expense_models_on_lines(self):
        """Link deferred models on lines before deferral generation (dates stay manual)."""
        for move in self.filtered(
            lambda m: m.is_purchase_document(include_receipts=True) or m.is_entry()
        ):
            for line in move.line_ids.filtered(lambda l: not l.display_type):
                model = line._get_deferred_expense_model()
                if model and not line.deferred_expense_model_id:
                    line.deferred_expense_model_id = model

    def _post(self, soft=True):
        self._prepare_deferred_expense_models_on_lines()
        return super()._post(soft)

    def _get_deferred_entries_method(self):
        """Journal entries with deferred expense models use expense generation settings."""
        self.ensure_one()
        if self.is_purchase_document():
            return self.company_id.generate_deferred_expense_entries_method
        if self.is_entry() and any(
            line.deferred_start_date
            and (
                line._get_deferred_expense_model()
                or line.account_id.internal_group == "expense"
            )
            for line in self.line_ids
        ):
            return self.company_id.generate_deferred_expense_entries_method
        return super()._get_deferred_entries_method()

    def _get_deferred_type_for_move(self):
        self.ensure_one()
        if self.is_purchase_document(include_receipts=True):
            return "expense"
        if self.is_sale_document(include_receipts=True):
            return "revenue"
        if self.is_entry() and any(
            line.deferred_start_date
            and (
                line._get_deferred_expense_model()
                or line.account_id.internal_group == "expense"
            )
            for line in self.line_ids
        ):
            return "expense"
        return "revenue"

    def _get_deferred_account_journal_for_line(self, line, deferred_type):
        """Return (deferred_account, deferred_journal) for a move line."""
        self.ensure_one()
        company = self.company_id
        model = line._get_deferred_expense_model() if deferred_type == "expense" else False

        if deferred_type == "expense":
            deferred_account = (
                model.deferred_expense_account_id
                if model and model.deferred_expense_account_id
                else company.deferred_expense_account_id
            )
            deferred_journal = (
                model.journal_id
                if model and model.journal_id
                else company.deferred_expense_journal_id
            )
        else:
            deferred_account = company.deferred_revenue_account_id
            deferred_journal = company.deferred_revenue_journal_id
        return deferred_account, deferred_journal, model

    def _generate_deferred_entries(self):
        """Generate deferred entries using per-line deferred expense models when set."""
        self.ensure_one()
        if self.state != "posted":
            return

        deferred_type = self._get_deferred_type_for_move()

        moves_vals_to_create = []
        lines_vals_to_create = []
        lines_periods = []
        for line in self.line_ids.filtered(lambda l: l.deferred_start_date and l.deferred_end_date):
            periods = line._get_deferred_periods()
            if not periods:
                continue

            deferred_account, deferred_journal, model = self._get_deferred_account_journal_for_line(
                line, deferred_type
            )
            if not deferred_journal:
                raise UserError(_("Please set the deferred journal in the accounting settings."))
            if not deferred_account:
                raise UserError(_("Please set the deferred accounts in the accounting settings."))

            start_date = line.deferred_start_date
            end_date = line.deferred_end_date
            accounting_date = line.date

            if line.company_id.deferred_expense_amount_computation_method == "full_months":
                if self._get_deferred_diff_dates(start_date.replace(day=1), end_date + relativedelta(days=1)) < 2:
                    end_date += relativedelta(months=-1)

            if start_date.replace(day=1) == end_date.replace(day=1) == accounting_date.replace(day=1):
                continue

            ref = _("Deferral of %s", line.move_id.name or "")

            move_vals = {
                "move_type": "entry",
                "deferred_original_move_ids": [Command.set(line.move_id.ids)],
                "journal_id": deferred_journal.id,
                "company_id": self.company_id.id,
                "partner_id": line.partner_id.id,
                "auto_post": "at_date",
                "ref": ref,
                "name": False,
                "date": line.move_id.date,
                "deferred_expense_model_id": model.id if model else False,
            }
            moves_vals_to_create.append(move_vals)
            lines_vals_to_create.append([
                {
                    **self.env["account.move.line"]._get_deferred_lines_values(
                        account.id, coeff * line.balance, ref, line.analytic_distribution, line
                    ),
                    "deferred_expense_model_id": model.id if model else False,
                }
                for (account, coeff) in [(line.account_id, -1), (deferred_account, 1)]
            ])
            lines_periods.append((line, periods, deferred_account, model))

        moves_fully_deferred = self.create(moves_vals_to_create)
        for move_fully_deferred, lines_vals in zip(moves_fully_deferred, lines_vals_to_create):
            for line_vals in lines_vals:
                line_vals["move_id"] = move_fully_deferred.id
        self.env["account.move.line"].create(list(chain(*lines_vals_to_create)))

        deferral_moves_vals = []
        deferral_moves_line_vals = []
        for (line, periods, deferred_account, model), move_vals in zip(
            lines_periods, moves_vals_to_create
        ):
            remaining_balance = line.balance
            for period_index, period in enumerate(periods):
                force_balance = remaining_balance if period_index == len(periods) - 1 else None
                deferred_amounts = self._get_deferred_amounts_by_line(line, [period], deferred_type)[0]
                balance = deferred_amounts[period] if force_balance is None else force_balance
                remaining_balance -= line.currency_id.round(balance)
                deferral_moves_vals.append({
                    **move_vals,
                    "date": period[1],
                    "deferred_expense_model_id": model.id if model else False,
                })
                deferral_moves_line_vals.append([
                    {
                        **self.env["account.move.line"]._get_deferred_lines_values(
                            account.id,
                            coeff * balance,
                            move_vals["ref"],
                            line.analytic_distribution,
                            line,
                        ),
                        "partner_id": line.partner_id.id,
                        "product_id": line.product_id.id,
                        "deferred_expense_model_id": model.id if model else False,
                    }
                    for (account, coeff) in [
                        (deferred_amounts["account_id"], 1),
                        (deferred_account, -1),
                    ]
                ])

        deferral_moves = self.create(deferral_moves_vals)
        for deferral_move, lines_vals in zip(deferral_moves, deferral_moves_line_vals):
            for line_vals in lines_vals:
                line_vals["move_id"] = deferral_move.id
        self.env["account.move.line"].create(list(chain(*deferral_moves_line_vals)))

        to_unlink = deferral_moves.filtered(lambda move: move.currency_id.is_zero(move.amount_total))
        to_unlink.unlink()

        (moves_fully_deferred + deferral_moves - to_unlink)._post(soft=True)
