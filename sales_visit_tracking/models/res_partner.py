# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    lead_id = fields.Many2one(
        'sales.visit.lead',
        string='Originating Lead',
        copy=False,
        index=True
    )

    visit_ids = fields.One2many(
        'sales.visit',
        'partner_id',
        string='Visits History'
    )

    latitude = fields.Float(
        string='Latitude',
        digits=(10, 7)
    )

    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7)
    )

    geo_verified = fields.Boolean(
        string='Geo Verified',
        default=False
    )

    geolocation_date = fields.Datetime(
        string='Geolocation Date'
    )
