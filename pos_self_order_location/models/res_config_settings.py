# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_self_ordering_url = fields.Char(
        string='Self-Order URL',
        related='pos_config_id.self_ordering_url',
        readonly=True,
    )
