# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sales_visit_allowed_radius = fields.Float(
        string='Allowed Radius (m)',
        config_parameter='sales_visit_tracking.allowed_radius',
        default=100.0,
        help="Maximum distance in meters from customer location to allow a valid check-in."
    )
    sales_visit_tracking_interval = fields.Integer(
        string='Route Tracking Interval (min)',
        config_parameter='sales_visit_tracking.tracking_interval',
        default=5,
        help="Interval in minutes for background coordinate route logging."
    )
