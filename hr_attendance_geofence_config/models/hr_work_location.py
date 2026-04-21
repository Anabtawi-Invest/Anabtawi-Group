from odoo import fields, models


class HrWorkLocation(models.Model):
    _inherit = 'hr.work.location'

    attendance_geo_latitude = fields.Float(
        related='address_id.partner_latitude',
        readonly=False,
        digits=(10, 7),
        string="Attendance Latitude",
    )
    attendance_geo_longitude = fields.Float(
        related='address_id.partner_longitude',
        readonly=False,
        digits=(10, 7),
        string="Attendance Longitude",
    )
    attendance_geo_radius_m = fields.Float(
        string="Allowed Radius (m)",
        default=200.0,
        help="Maximum distance in meters from this work location to allow check-in.",
    )
