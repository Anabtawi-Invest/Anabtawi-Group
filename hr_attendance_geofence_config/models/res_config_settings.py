# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    attendance_geo_enforce = fields.Boolean(
        related='company_id.attendance_geo_enforce',
        readonly=False,
    )
    attendance_geo_latitude = fields.Float(
        related='company_id.attendance_geo_latitude',
        readonly=False,
    )
    attendance_geo_longitude = fields.Float(
        related='company_id.attendance_geo_longitude',
        readonly=False,
    )
    attendance_geo_radius_m = fields.Float(
        related='company_id.attendance_geo_radius_m',
        readonly=False,
    )
