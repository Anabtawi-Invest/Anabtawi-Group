# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    deferred_expense_model_id = fields.Many2one(
        "deferred.expense.model",
        string="Deferred Expense Model",
        check_company=True,
        copy=False,
        help="Deferred expense model applied on this line. "
             "Filled from the product when available, or set manually on journal entries.",
    )

    def _get_deferred_expense_model(self):
        self.ensure_one()
        return self.deferred_expense_model_id or self.product_id.product_tmpl_id.deferred_expense_model_id

    def _can_apply_deferred_expense_model(self):
        self.ensure_one()
        return self.move_id.is_purchase_document(include_receipts=True) or self.move_id.is_entry()

    def _apply_deferred_expense_model(self, model=None):
        """Apply accounts, analytic and deferred dates from the model."""
        for line in self:
            if not line._can_apply_deferred_expense_model():
                continue
            dem = model or line._get_deferred_expense_model()
            if not dem:
                continue
            line.deferred_expense_model_id = dem
            if dem.expense_account_id:
                line.account_id = dem.expense_account_id
            if dem.analytic_account_id:
                line.analytic_distribution = {str(dem.analytic_account_id.id): 100.0}
            start = (
                line.move_id.invoice_date
                or line.move_id.date
                or fields.Date.context_today(line)
            )
            line.deferred_start_date = start
            line.deferred_end_date = (
                start + relativedelta(months=dem.recognition_months) - relativedelta(days=1)
            )

    def _has_deferred_compatible_account(self):
        """Allow deferred dates on journal entries when a deferred expense model is set."""
        self.ensure_one()
        if self.deferred_expense_model_id and self.move_id.is_entry():
            return True
        return super()._has_deferred_compatible_account()

    @api.onchange("product_id")
    def _onchange_product_id_deferred_expense_model(self):
        for line in self:
            if not line.product_id:
                continue
            model = line.product_id.product_tmpl_id.deferred_expense_model_id
            if model:
                line._apply_deferred_expense_model(model)

    @api.onchange("deferred_expense_model_id")
    def _onchange_deferred_expense_model_id(self):
        for line in self:
            if line.deferred_expense_model_id:
                line._apply_deferred_expense_model(line.deferred_expense_model_id)
