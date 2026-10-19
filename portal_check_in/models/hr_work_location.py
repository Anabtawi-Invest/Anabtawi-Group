# -*- coding: utf-8 -*-

from odoo import fields, models


class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    attendance_geo_enforce = fields.Boolean(
        string="Enforce Attendance Geofence",
        help="If enabled, portal check-in is allowed only within the configured radius for this work location.",
    )
    attendance_geo_latitude = fields.Float(
        string="Latitude",
        digits=(10, 7),
    )
    attendance_geo_longitude = fields.Float(
        string="Longitude",
        digits=(10, 7),
    )
    attendance_geo_radius_m = fields.Float(
        string="Allowed Radius (m)",
        help="Maximum allowed distance in meters from this work location for portal check-in.",
    )
