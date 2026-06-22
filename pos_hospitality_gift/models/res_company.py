from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    gift_expense_account_id = fields.Many2one(
        "account.account",
        string="Hospitality Expense Account",
        check_company=True,
        domain="[('deprecated', '=', False)]",
    )
