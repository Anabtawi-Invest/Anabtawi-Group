from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gift_expense_account_id = fields.Many2one(
        "account.account",
        related="company_id.gift_expense_account_id",
        readonly=False,
        check_company=True,
    )
