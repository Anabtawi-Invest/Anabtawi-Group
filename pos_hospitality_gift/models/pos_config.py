from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    gift_expense_account_id = fields.Many2one(
        "account.account",
        related="company_id.gift_expense_account_id",
        readonly=False,
        check_company=True,
    )
