from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    hospitality_payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="Hospitality Payment Method",
        check_company=True,
        domain="[('type', '=', 'pay_later')]",
        help="Payment method used when the company sponsors gift orders.",
    )
    hospitality_clearing_account_id = fields.Many2one(
        "account.account",
        string="Hospitality Clearing Account",
        check_company=True,
        domain="[('deprecated', '=', False)]",
    )
    gift_expense_account_id = fields.Many2one(
        "account.account",
        string="Gift Expense Account",
        check_company=True,
        domain="[('deprecated', '=', False)]",
    )
    auto_suggest_hospitality_payment = fields.Boolean(
        string="Auto Suggest Hospitality Payment",
        help="Suggest Hospitality payment on the payment screen when at least one gift line exists.",
    )
