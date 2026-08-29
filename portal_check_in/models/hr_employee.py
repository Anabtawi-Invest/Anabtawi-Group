# -*- coding: utf-8 -*-

import logging
import math
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    portal_attendance_lock_until = fields.Datetime(
        string="Portal Attendance Lock Until",
        copy=False,
        help="If set, this employee cannot submit another portal attendance action until this time.",
    )

    allow_remote_attendance = fields.Boolean(
        string="Allow Check-in From Any Location",
        help="If enabled, this employee can check in from any location and geofence "
             "restrictions are skipped.",
    )
    attendance_work_location_ids = fields.Many2many(
        "hr.work.location",
        "hr_employee_attendance_work_location_rel",
        "employee_id",
        "work_location_id",
        string="Allowed Attendance Work Locations",
        help="Portal check-in is allowed when the employee is inside the geofence "
             "of any of these work locations (each location uses its own lat/lon/radius).",
    )

    def _acquire_portal_attendance_action_lock(self, lock_minutes=10):
        self.ensure_one()
        _logger.info(
            "portal_check_in lock acquire requested: employee_id=%s lock_minutes=%s",
            self.id,
            lock_minutes,
        )
        self.env.cr.execute(
            """
                SELECT portal_attendance_lock_until
                FROM hr_employee
                WHERE id = %s
                FOR UPDATE
            """,
            (self.id,),
        )
        row = self.env.cr.fetchone()
        lock_until = row and row[0]
        now = fields.Datetime.now()
        _logger.info(
            "portal_check_in lock read: employee_id=%s lock_until=%s now=%s is_locked=%s",
            self.id,
            lock_until,
            now,
            bool(lock_until and lock_until > now),
        )
        if lock_until and lock_until > now:
            _logger.warning(
                "portal_check_in lock blocked request: employee_id=%s lock_until=%s now=%s",
                self.id,
                lock_until,
                now,
            )
            raise UserError(
                _(
                    "Attendance action already submitted. Please wait 10 minutes before trying again."
                )
            )
        new_lock_until = now + timedelta(minutes=lock_minutes)
        self.write({'portal_attendance_lock_until': new_lock_until})
        _logger.info(
            "portal_check_in lock set: employee_id=%s new_lock_until=%s",
            self.id,
            new_lock_until,
        )

    def _release_portal_attendance_action_lock(self):
        self.ensure_one()
        old_lock_until = self.portal_attendance_lock_until
        self.write({'portal_attendance_lock_until': False})
        _logger.info(
            "portal_check_in lock released: employee_id=%s previous_lock_until=%s",
            self.id,
            old_lock_until,
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

    def _get_portal_geofence_work_locations(self):
        """Return work locations used to validate portal check-in geofence."""
        self.ensure_one()
        if self.allow_remote_attendance:
            return self.env["hr.work.location"]

        def _has_coordinates(location):
            return (
                self._safe_float(location.attendance_geo_latitude) is not None
                and self._safe_float(location.attendance_geo_longitude) is not None
            )

        # Preferred: locations explicitly allowed on the employee profile.
        if self.attendance_work_location_ids:
            return self.attendance_work_location_ids.filtered(_has_coordinates)

        # Backward compatibility: fall back to the single work location.
        if self.work_location_id and self.work_location_id.attendance_geo_enforce:
            return self.work_location_id.filtered(_has_coordinates)

        return self.env["hr.work.location"]

    def _get_portal_geofence_work_location(self):
        """Deprecated single-location helper; kept for compatibility."""
        return self._get_portal_geofence_work_locations()[:1]

    def _is_portal_geo_tracking_required(self):
        self.ensure_one()
        if self.allow_remote_attendance:
            return False
        if self.attendance_work_location_ids:
            return True
        return bool(self._get_portal_geofence_work_locations())

    def _check_portal_geo_restriction(self, geo_information=None):
        self.ensure_one()
        # Restrict only check-in; check-out remains unchanged.
        if self.allow_remote_attendance:
            return

        if self.attendance_work_location_ids and not self._get_portal_geofence_work_locations():
            raise UserError(_(
                "تم تحديد مواقع دوام للموظف، لكن إحداثياتها (خط العرض/خط الطول) غير مضبوطة."
            ))

        work_locations = self._get_portal_geofence_work_locations()
        if not work_locations:
            return

        payload = geo_information or {}
        employee_lat = self._safe_float(payload.get('latitude'))
        employee_lon = self._safe_float(payload.get('longitude'))
        if employee_lat is None or employee_lon is None:
            raise UserError(_(
                "تعذر التحقق من موقعك. يرجى تفعيل إذن الموقع ثم المحاولة مرة أخرى."
            ))

        nearest_distance_m = None
        nearest_radius_m = None
        for work_location in work_locations:
            location_lat = self._safe_float(work_location.attendance_geo_latitude)
            location_lon = self._safe_float(work_location.attendance_geo_longitude)
            radius_m = self._safe_float(work_location.attendance_geo_radius_m) or 0.0
            distance_m = self._haversine_distance_m(
                employee_lat, employee_lon, location_lat, location_lon
            )
            if distance_m <= radius_m:
                return
            if nearest_distance_m is None or distance_m < nearest_distance_m:
                nearest_distance_m = distance_m
                nearest_radius_m = radius_m

        raise UserError(_(
            "تم رفض تسجيل الحضور: أنت خارج النطاق المسموح لمواقع الدوام المحددة. "
            "أقرب مسافة %.0f متر، وأقرب نطاق مسموح %.0f متر."
        ) % (nearest_distance_m or 0.0, nearest_radius_m or 0.0))

    def _attendance_action_change(self, geo_information=None):
        self.ensure_one()
        if self.attendance_state != 'checked_in':
            self._check_portal_geo_restriction(geo_information=geo_information)
        return super()._attendance_action_change(geo_information=geo_information)
