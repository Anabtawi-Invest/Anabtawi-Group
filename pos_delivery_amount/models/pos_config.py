from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    delivery_intermediate_account_id = fields.Many2one(
        "account.account",
        string="Delivery Intermediate Account",
        check_company=True,
    )
    delivery_journal_id = fields.Many2one(
        "account.journal",
        string="Delivery Journal",
        domain="[('type', '=', 'general')]",
        check_company=True,
    )
    main_holding_cash_fund_account_id = fields.Many2one(
        "account.account",
        string="Main Holding Cash Fund",
        check_company=True,
    )
    delivery_amount_difference_account_id = fields.Many2one(
        "account.account",
        string="Differences between Delivery Amount and Real Amount",
        domain=[
            (
                "account_type",
                "in",
                [
                    "asset_receivable",
                    "asset_cash",
                    "asset_current",
                    "asset_non_current",
                    "asset_prepayments",
                    "fixed_assets",
                    "liability_payable",
                    "liability_credit_card",
                    "liability_current",
                    "liability_non_current",
                ],
            )
        ],
        check_company=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        # Core POS uses [] to mean "load all fields"; keep that behavior.
        if not fields_list:
            return fields_list
        for field_name in ("delivery_journal_id", "delivery_intermediate_account_id"):
            if field_name not in fields_list:
                fields_list.append(field_name)
        return fields_list
