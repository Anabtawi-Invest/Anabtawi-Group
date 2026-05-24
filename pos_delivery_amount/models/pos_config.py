# pos_delivery_amount/models/pos_config.py

from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    delivery_intermediate_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Intermediate Account',
        help='Temporary holding account for undeposited cash pending bank delivery.',
        tracking=True,
    )

    delivery_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Delivery Journal',
        domain=[('type', '=', 'general')],
        help='Miscellaneous journal used to post the delivery amount accounting entry.',
        tracking=True,
    )
