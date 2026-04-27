# -*- coding: utf-8 -*-

import logging
import math
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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

    def _get_portal_geofence_work_location(self):
        self.ensure_one()
        work_location = self.work_location_id
        if not work_location or self.allow_remote_attendance:
            return self.env["hr.work.location"]
        return work_location if work_location.attendance_geo_enforce else self.env["hr.work.location"]

    def _is_portal_geo_tracking_required(self):
        self.ensure_one()
        return bool(self._get_portal_geofence_work_location())

    def _check_portal_geo_restriction(self, geo_information=None):
        self.ensure_one()
        # Restrict only check-in; check-out remains unchanged.
        work_location = self._get_portal_geofence_work_location()
        if work_location:
            location_lat = self._safe_float(work_location.attendance_geo_latitude)
            location_lon = self._safe_float(work_location.attendance_geo_longitude)
            radius_m = self._safe_float(work_location.attendance_geo_radius_m) or 0.0
            if location_lat is None or location_lon is None:
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
                employee_lat, employee_lon, location_lat, location_lon
            )
            if distance_m > radius_m:
                raise UserError(_(
                    "تم رفض تسجيل الحضور: أنت خارج النطاق المسموح لموقع الدوام. "
                    "المسافة الحالية %.0f متر، والنطاق المسموح %.0f متر."
                ) % (distance_m, radius_m))

    def _get_available_overtime_authorization_request(self):
        self.ensure_one()
        approval_model = self.env["approval.request"]
        if not hasattr(type(approval_model), "_get_available_preauthorized_request"):
            return self.env["approval.request"]
        target_date = fields.Date.context_today(self)
        return approval_model._get_available_preauthorized_request(
            self, target_date=target_date
        )

    def _create_authorized_attendance(self, action_date, geo_information, approval_request):
        self.ensure_one()
        vals = {
            "employee_id": self.id,
            "check_in": action_date,
            "overtime_authorization_request_id": approval_request.id,
            "overtime_authorization_deadline": action_date + timedelta(hours=approval_request.quantity),
        }
        if geo_information:
            vals.update(
                {"in_%s" % key: geo_information[key] for key in geo_information}
            )
        attendance = self.env["hr.attendance"].create(vals)
        approval_request._reserve_preauthorized_attendance(attendance)
        _logger.warning(
            "portal_check_in authorized check-in: employee_id=%s attendance_id=%s request_id=%s "
            "request_status=%s quantity=%s check_in=%s deadline=%s geo_keys=%s",
            self.id,
            attendance.id,
            approval_request.id,
            approval_request.request_status,
            approval_request.quantity,
            attendance.check_in,
            attendance.overtime_authorization_deadline,
            sorted(geo_information.keys()) if geo_information else [],
        )
        return attendance

    def _check_overtime_gate_before_check_in(self):
        self.ensure_one()
        if not hasattr(type(self), "_is_weekly_hours_threshold_reached"):
            return False
        if not self._is_weekly_hours_threshold_reached():
            return False

        approval_request = self._get_available_overtime_authorization_request()
        if approval_request:
            return approval_request

        raise UserError(
            _(
                "You reached the weekly worked hours limit. You must obtain an approved overtime request before checking in again."
            )
        )

    def _apply_authorized_check_out(self, attendance, action_date, geo_information):
        self.ensure_one()
        check_out_date = action_date
        if attendance.overtime_authorization_deadline:
            check_out_date = min(action_date, attendance.overtime_authorization_deadline)
        _logger.warning(
            "portal_check_in authorized check-out start: employee_id=%s attendance_id=%s request_id=%s "
            "action_date=%s deadline=%s final_check_out=%s current_worked_hours=%s geo_keys=%s",
            self.id,
            attendance.id,
            attendance.overtime_authorization_request_id.id,
            action_date,
            attendance.overtime_authorization_deadline,
            check_out_date,
            attendance.worked_hours,
            sorted(geo_information.keys()) if geo_information else [],
        )

        vals = {"check_out": check_out_date}
        if geo_information:
            vals.update({"out_%s" % key: geo_information[key] for key in geo_information})
        attendance.write(vals)
        attendance._finalize_overtime_authorization()
        attendance.invalidate_recordset(
            ["worked_hours", "linked_overtime_ids", "overtime_hours", "validated_overtime_hours", "overtime_status"]
        )
        _logger.warning(
            "portal_check_in authorized check-out done: employee_id=%s attendance_id=%s request_id=%s "
            "check_in=%s check_out=%s worked_hours=%s linked_overtime_ids=%s overtime_hours=%s "
            "validated_overtime_hours=%s overtime_status=%s",
            self.id,
            attendance.id,
            attendance.overtime_authorization_request_id.id,
            attendance.check_in,
            attendance.check_out,
            attendance.worked_hours,
            attendance.linked_overtime_ids.ids,
            attendance.overtime_hours,
            attendance.validated_overtime_hours,
            attendance.overtime_status,
        )
        return attendance

    def _attendance_action_change(self, geo_information=None):
        self.ensure_one()

        if self.attendance_state != 'checked_in':
            self._check_portal_geo_restriction(geo_information=geo_information)
            approval_request = self._check_overtime_gate_before_check_in()
            if approval_request:
                return self._create_authorized_attendance(
                    fields.Datetime.now(), geo_information, approval_request
                )
            return super()._attendance_action_change(geo_information=geo_information)

        attendance = self.env['hr.attendance'].search(
            [('employee_id', '=', self.id), ('check_out', '=', False)], limit=1
        )
        if attendance and attendance.overtime_authorization_request_id:
            return self._apply_authorized_check_out(
                attendance, fields.Datetime.now(), geo_information
            )

        return super()._attendance_action_change(geo_information=geo_information)
