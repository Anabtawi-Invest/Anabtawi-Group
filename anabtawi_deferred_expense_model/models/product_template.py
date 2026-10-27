# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    deferred_expense_model_id = fields.Many2one(
        "deferred.expense.model",
        string="Deferred Expense Model",
        help="When set, vendor bill lines using this product apply this model's "
             "expense account, deferred dates, and prepaid account.",
    )
