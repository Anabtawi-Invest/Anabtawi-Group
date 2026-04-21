# -*- coding: utf-8 -*-

import math

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    allow_remote_attendance = fields.Boolean(
        string="Allow Check-in From Any Location",
        help="If enabled, this employee can check in from any location and geofence "
             "restrictions are skipped.",
    )

    @staticmethod
    def _safe_float(value):
        try:
            if value in (False, None, ''):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _haversine_distance_m(lat1, lon1, lat2, lon2):
        # Distance between two points on earth in meters.
        radius_earth_m = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return radius_earth_m * c

    def _get_attendance_geofence_target(self):
        self.ensure_one()

        if self.work_location_id:
            return {
                'name': self.work_location_id.display_name,
                'kind': 'work_location',
                'latitude': self._safe_float(self.work_location_id.attendance_geo_latitude),
                'longitude': self._safe_float(self.work_location_id.attendance_geo_longitude),
                'radius_m': self._safe_float(self.work_location_id.attendance_geo_radius_m)
                    or self._safe_float(self.company_id.attendance_geo_radius_m)
                    or 0.0,
            }

        return {
            'name': self.company_id.display_name,
            'kind': 'company',
            'latitude': self._safe_float(self.company_id.attendance_geo_latitude),
            'longitude': self._safe_float(self.company_id.attendance_geo_longitude),
            'radius_m': self._safe_float(self.company_id.attendance_geo_radius_m) or 0.0,
        }

    def _attendance_action_change(self, geo_information=None):
        self.ensure_one()

        # Restrict only check-in; check-out remains unchanged.
        if self.attendance_state != 'checked_in':
            company = self.company_id
            if company.attendance_geo_enforce and not self.allow_remote_attendance:
                if not company.attendance_device_tracking:
                    raise UserError(_(
                        "تقييد الحضور حسب موقع العمل يتطلب تفعيل خيار تتبع الجهاز والموقع."
                    ))

                geofence_target = self._get_attendance_geofence_target()
                target_lat = geofence_target['latitude']
                target_lon = geofence_target['longitude']
                radius_m = geofence_target['radius_m']
                if target_lat is None or target_lon is None:
                    if geofence_target['kind'] == 'work_location':
                        raise UserError(_(
                            "تم تفعيل نطاق الحضور، لكن إحداثيات موقع العمل المحدد للموظف غير مضبوطة."
                        ))
                    raise UserError(_(
                        "تم تفعيل نطاق الحضور، لكن إحداثيات الشركة الاحتياطية غير مضبوطة."
                    ))

                payload = geo_information or {}
                employee_lat = self._safe_float(payload.get('latitude'))
                employee_lon = self._safe_float(payload.get('longitude'))
                if employee_lat is None or employee_lon is None:
                    raise UserError(_(
                        "تعذر التحقق من موقعك. يرجى تفعيل إذن الموقع ثم المحاولة مرة أخرى."
                    ))

                distance_m = self._haversine_distance_m(
                    employee_lat, employee_lon, target_lat, target_lon
                )
                if distance_m > radius_m:
                    location_label = _("موقع العمل") if geofence_target['kind'] == 'work_location' else _("موقع الشركة")
                    raise UserError(_(
                        "تم رفض تسجيل الحضور: أنت خارج النطاق المسموح لـ %s. "
                        "المسافة الحالية %.0f متر، والنطاق المسموح %.0f متر."
                    ) % (location_label, distance_m, radius_m))

        return super()._attendance_action_change(geo_information=geo_information)
