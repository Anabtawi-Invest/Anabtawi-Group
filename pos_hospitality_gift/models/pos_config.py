from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    hospitality_payment_method_id = fields.Many2one(
        "pos.payment.method",
        related="company_id.hospitality_payment_method_id",
        readonly=False,
        check_company=True,
    )
    auto_suggest_hospitality_payment = fields.Boolean(
        related="company_id.auto_suggest_hospitality_payment",
        readonly=False,
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

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        if "hospitality_payment_method_id" not in fields_to_load:
            fields_to_load.append("hospitality_payment_method_id")
        if "auto_suggest_hospitality_payment" not in fields_to_load:
            fields_to_load.append("auto_suggest_hospitality_payment")
        return fields_to_load
