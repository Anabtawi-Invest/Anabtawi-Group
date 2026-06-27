from odoo import fields, models


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
