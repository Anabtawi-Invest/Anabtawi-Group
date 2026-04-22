# -*- coding: utf-8 -*-

from odoo import fields, models


class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    geo_latitude = fields.Float(
        string="Latitude",
        digits=(10, 7),
        related="address_id.partner_latitude",
        readonly=False,
    )
    geo_longitude = fields.Float(
        string="Longitude",
        digits=(10, 7),
        related="address_id.partner_longitude",
        readonly=False,
    )
