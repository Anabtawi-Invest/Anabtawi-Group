# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompanyGeofenceLocation(models.Model):
    _name = 'res.company.geofence.location'
    _description = 'Company Attendance Geofence Location'
    _order = 'sequence, id'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(
        string='Location Name',
        required=True,
        default='Location',
    )
    latitude = fields.Float(
        string='Latitude',
        digits=(10, 7),
        required=True,
    )
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7),
        required=True,
    )
    radius_m = fields.Float(
        string='Allowed Radius (m)',
        default=200.0,
        required=True,
        help='Maximum allowed distance in meters from this location for check-in.',
    )
