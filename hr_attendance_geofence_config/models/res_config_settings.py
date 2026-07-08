# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    attendance_geo_enforce = fields.Boolean(
        related='company_id.attendance_geo_enforce',
        readonly=False,
    )
    attendance_geo_location_ids = fields.One2many(
        related='company_id.attendance_geo_location_ids',
        readonly=False,
    )
