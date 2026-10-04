# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosCategory(models.Model):
    _inherit = 'pos.category'

    hide_in_pos_ui = fields.Boolean(
        string="Hide in POS UI",
        help="Hide this category and its products from the POS screen. "
             "The products still appear when searched.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ['hide_in_pos_ui']
