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
