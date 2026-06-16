from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_hospitality_payment_method_id = fields.Many2one(
        "pos.payment.method",
        related="pos_config_id.hospitality_payment_method_id",
        readonly=False,
        check_company=True,
        string="Hospitality Payment Method",
    )
    hospitality_clearing_account_id = fields.Many2one(
        "account.account",
        related="company_id.hospitality_clearing_account_id",
        readonly=False,
        check_company=True,
    )
    gift_expense_account_id = fields.Many2one(
        "account.account",
        related="company_id.gift_expense_account_id",
        readonly=False,
        check_company=True,
    )
    auto_suggest_hospitality_payment = fields.Boolean(
        related="company_id.auto_suggest_hospitality_payment",
        readonly=False,
    )
