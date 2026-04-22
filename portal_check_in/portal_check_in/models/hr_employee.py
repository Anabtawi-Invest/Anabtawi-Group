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

    def _attendance_action_change(self, geo_information=None):
        self.ensure_one()

        # Restrict only check-in; check-out remains unchanged.
        if self.attendance_state != 'checked_in':
            company = self.company_id
            if company.attendance_geo_enforce and not self.allow_remote_attendance:
                if not company.attendance_device_tracking:
                    raise UserError(_(
                        "تقييد الحضور حسب موقع الشركة يتطلب تفعيل خيار تتبع الجهاز والموقع."
                    ))

                work_location = self.work_location_id
                work_location_address = work_location.address_id
                if not work_location or not work_location_address:
                    raise UserError(_(
                        "تم تفعيل نطاق موقع الدوام، لكن الموظف لا يملك موقع دوام/عنوان دوام محدد."
                    ))
                work_location_lat = self._safe_float(work_location.geo_latitude)
                work_location_lon = self._safe_float(work_location.geo_longitude)
                radius_m = self._safe_float(company.attendance_geo_radius_m) or 0.0
                if work_location_lat is None or work_location_lon is None:
                    raise UserError(_(
                        "تم تفعيل نطاق موقع الدوام، لكن إحداثيات موقع الدوام (خط العرض/خط الطول) غير مضبوطة."
                    ))

                payload = geo_information or {}
                employee_lat = self._safe_float(payload.get('latitude'))
                employee_lon = self._safe_float(payload.get('longitude'))
                if employee_lat is None or employee_lon is None:
                    raise UserError(_(
                        "تعذر التحقق من موقعك. يرجى تفعيل إذن الموقع ثم المحاولة مرة أخرى."
                    ))

                distance_m = self._haversine_distance_m(
                    employee_lat, employee_lon, work_location_lat, work_location_lon
                )
                if distance_m > radius_m:
                    raise UserError(_(
                        "تم رفض تسجيل الحضور: أنت خارج النطاق المسموح لموقع الدوام. "
                        "المسافة الحالية %.0f متر، والنطاق المسموح %.0f متر."
                    ) % (distance_m, radius_m))

        return super()._attendance_action_change(geo_information=geo_information)
