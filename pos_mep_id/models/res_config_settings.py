# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_mep_payment_method_ids = fields.Many2many(
        "pos.payment.method",
        related="pos_config_id.mep_payment_method_ids",
        readonly=False,
        string="MEP Payment Methods",
    )
