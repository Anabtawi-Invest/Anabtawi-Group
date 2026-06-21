# -*- coding: utf-8 -*-

from odoo import fields, models


class SalesRoutePoint(models.Model):
    _name = 'sales.route.point'
    _description = 'Route GPS Log Point'
    _order = 'timestamp desc'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True
    )
    visit_id = fields.Many2one(
        'sales.visit',
        string='Visit',
        ondelete='set null'
    )
    timestamp = fields.Datetime(
        string='Timestamp',
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    latitude = fields.Float(
        string='Latitude',
        digits=(10, 7),
        required=True
    )
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7),
        required=True
    )
    speed = fields.Float(
        string='Speed (km/h)'
    )
    heading = fields.Float(
        string='Heading (Degrees)'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
