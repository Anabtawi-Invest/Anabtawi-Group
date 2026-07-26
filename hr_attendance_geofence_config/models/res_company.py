# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    attendance_geo_enforce = fields.Boolean(
        string="Restrict Attendance by Company Location",
        default=False,
        help="If enabled, check-in is only allowed inside the configured company radius "
             "unless the employee is marked as allowed for remote attendance.",
    )
    attendance_geo_latitude = fields.Float(
        string="Company Latitude",
        digits=(10, 7),
    )
    attendance_geo_longitude = fields.Float(
        string="Company Longitude",
        digits=(10, 7),
    )
    attendance_geo_radius_m = fields.Float(
        string="Allowed Radius (m)",
        default=200.0,
        help="Maximum distance in meters from company location to allow check-in.",
    )
