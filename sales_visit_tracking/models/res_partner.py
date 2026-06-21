# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    lead_id = fields.Many2one(
        'sales.visit.lead',
        string='Originating Lead',
        copy=False
    )
    visit_ids = fields.One2many(
        'sales.visit',
        string='Visits History',
        compute='_compute_visit_ids'
    )
    latitude = fields.Float(
        string='Latitude',
        digits=(10, 7),
        help="GPS Latitude coordinate of customer."
    )
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7),
        help="GPS Longitude coordinate of customer."
    )
    geo_verified = fields.Boolean(
        string='Geo Verified',
        default=False
    )
    geolocation_date = fields.Datetime(
        string='Geolocation Date'
    )

    def _compute_visit_ids(self):
        for partner in self:
            if partner.lead_id:
                partner.visit_ids = self.env['sales.visit'].search([('lead_id', '=', partner.lead_id.id)])
            else:
                partner.visit_ids = self.env['sales.visit']
