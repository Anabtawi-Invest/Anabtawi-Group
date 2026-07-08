# -*- coding: utf-8 -*-

import math

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    attendance_geo_enforce = fields.Boolean(
        string="Restrict Attendance by Company Location",
        default=False,
        help="If enabled, check-in is only allowed inside at least one configured "
             "company location unless the employee is marked as allowed for remote attendance.",
    )
    attendance_geo_location_ids = fields.One2many(
        'res.company.geofence.location',
        'company_id',
        string='Attendance Geofence Locations',
        help="Employees can check in when they are inside the radius of any of these locations.",
    )

    @staticmethod
    def _haversine_distance_m(lat1, lon1, lat2, lon2):
        radius_earth_m = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return radius_earth_m * c

    def _get_valid_attendance_geofence_locations(self):
        self.ensure_one()
        return self.attendance_geo_location_ids.filtered(
            lambda location: location.latitude and location.longitude and location.radius_m > 0
        )

    def _is_within_attendance_geofence(self, latitude, longitude):
        self.ensure_one()
        locations = self._get_valid_attendance_geofence_locations()
        if not locations:
            return False, 0.0, 0.0

        closest_distance_m = None
        closest_radius_m = 0.0
        for location in locations:
            distance_m = self._haversine_distance_m(
                latitude, longitude, location.latitude, location.longitude
            )
            if distance_m <= location.radius_m:
                return True, distance_m, location.radius_m
            if closest_distance_m is None or distance_m < closest_distance_m:
                closest_distance_m = distance_m
                closest_radius_m = location.radius_m

        return False, closest_distance_m or 0.0, closest_radius_m
