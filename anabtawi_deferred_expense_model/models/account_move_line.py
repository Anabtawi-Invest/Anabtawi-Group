# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    deferred_expense_model_id = fields.Many2one(
        "deferred.expense.model",
        string="Deferred Expense Model",
        check_company=True,
        copy=False,
        help="Deferred expense model applied on this line. "
             "Filled from the product when available, or set manually on journal entries. "
             "Deferred start/end dates must be entered manually.",
    )

    def _get_deferred_expense_model(self):
        self.ensure_one()
        return self.deferred_expense_model_id or self.product_id.product_tmpl_id.deferred_expense_model_id

    def _can_apply_deferred_expense_model(self):
        self.ensure_one()
        return self.move_id.is_purchase_document(include_receipts=True) or self.move_id.is_entry()

    def _apply_deferred_expense_model(self, model=None):
        """Apply expense account and analytic from the model. Dates stay manual."""
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

    def _has_deferred_compatible_account(self):
        """Allow deferred dates on journal entries when a deferred expense model is set."""
        self.ensure_one()
        if self.deferred_expense_model_id and self.move_id.is_entry():
            return True
        return super()._has_deferred_compatible_account()

    def _deferred_expense_model_for_account(self):
        """The single active model whose expense account is this line's account."""
        self.ensure_one()
        if not self.account_id:
            return self.env["deferred.expense.model"]
        company = self.company_id or self.move_id.company_id or self.env.company
        matches = self.env["deferred.expense.model"].search([
            ("expense_account_id", "=", self.account_id.id),
            ("company_id", "=", company.id),
        ])
        return matches if len(matches) == 1 else self.env["deferred.expense.model"]

    @api.onchange("account_id")
    def _onchange_account_id_deferred_expense_model(self):
        for line in self:
            if not line._can_apply_deferred_expense_model():
                continue
            model = line._deferred_expense_model_for_account()
            if model:
                if line.deferred_expense_model_id != model:
                    line.deferred_expense_model_id = model
            elif (
                line.deferred_expense_model_id
                and line.deferred_expense_model_id.expense_account_id != line.account_id
            ):
                line.deferred_expense_model_id = False

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
