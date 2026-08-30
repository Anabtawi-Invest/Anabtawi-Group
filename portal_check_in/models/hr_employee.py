# -*- coding: utf-8 -*-

import logging
import math
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


PORTAL_ATTENDANCE_LOCK_MINUTES = 2


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

    def _acquire_portal_attendance_action_lock(self, lock_minutes=PORTAL_ATTENDANCE_LOCK_MINUTES):
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
                    "Attendance action already submitted. Please wait %(minutes)s minutes before trying again."
                ) % {'minutes': lock_minutes}
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
        """Return work locations used to validate portal check-in and check-out geofence."""
        self.ensure_one()
        if self.allow_remote_attendance:
            return self.env["hr.work.location"]

        def _has_coordinates(location):
            return (
                self._safe_float(location.attendance_geo_latitude) is not None
                and self._safe_float(location.attendance_geo_longitude) is not None
                and (self._safe_float(location.attendance_geo_radius_m) or 0.0) > 0.0
            )

        # 1. Preferred: locations explicitly allowed on the employee profile.
        if self.attendance_work_location_ids:
            return self.attendance_work_location_ids.filtered(_has_coordinates)

        # 2. Fall back to the primary work location.
        if self.work_location_id:
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
        if self.work_location_id:
            return True
        return bool(self._get_portal_geofence_work_locations())

    def _check_portal_geo_restriction(self, geo_information=None):
        self.ensure_one()
        if self.allow_remote_attendance:
            return

        if self.attendance_work_location_ids and not self._get_portal_geofence_work_locations():
            raise UserError(_(
                "تم تحديد مواقع دوام للموظف، لكن إحداثياتها (خط العرض/خط الطول/نصف القطر) غير مضبوطة."
            ))

        work_locations = self._get_portal_geofence_work_locations()
        if not work_locations:
            if self.work_location_id and not self.attendance_work_location_ids:
                raise UserError(_(
                    "لم يتم ضبط إحداثيات ونطاق موقع العمل المحدد للموظف (%s)."
                ) % self.work_location_id.name)
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

        action_name = "تسجيل الانصراف" if self.attendance_state == 'checked_in' else "تسجيل الحضور"
        raise UserError(_(
            "تم رفض %(action)s: أنت خارج النطاق المسموح لمواقع الدوام المحددة. "
            "أقرب مسافة %(dist).0f متر، وأقرب نطاق مسموح %(rad).0f متر."
        ) % {
            'action': action_name,
            'dist': nearest_distance_m or 0.0,
            'rad': nearest_radius_m or 0.0,
        })

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
        deadline = False
        if not approval_request.overtime_disable_auto_checkout:
            deadline = action_date + timedelta(hours=approval_request.quantity)
        quantity_hours = approval_request.quantity or 0.0
        _logger.warning(
            "[PortalOTDebug] authorized_check_in_prepare employee_id=%s approval_request_id=%s "
            "request_status=%s quantity_hours=%s disable_auto_checkout=%s check_in=%s deadline=%s delta_seconds=%s",
            self.id,
            approval_request.id,
            approval_request.request_status,
            quantity_hours,
            approval_request.overtime_disable_auto_checkout,
            action_date,
            deadline,
            ((deadline - action_date).total_seconds() if deadline else False),
        )
        if deadline and deadline <= action_date:
            _logger.warning(
                "[PortalOTDebug] authorized_check_in_deadline_not_after_check_in employee_id=%s "
                "approval_request_id=%s quantity_hours=%s check_in=%s deadline=%s",
                self.id,
                approval_request.id,
                quantity_hours,
                action_date,
                deadline,
            )
        vals = {
            "employee_id": self.id,
            "check_in": action_date,
            "overtime_authorization_request_id": approval_request.id,
            "overtime_authorization_deadline": deadline,
        }
        if geo_information:
            vals.update(
                {"in_%s" % key: geo_information[key] for key in geo_information}
            )
        attendance = self.env["hr.attendance"].create(vals)
        approval_request._reserve_preauthorized_attendance(attendance)
        _logger.warning(
            "[PortalOTDebug] authorized_check_in_created employee_id=%s attendance_id=%s request_id=%s "
            "request_status=%s quantity=%s disable_auto_checkout=%s check_in=%s deadline=%s geo_keys=%s",
            self.id,
            attendance.id,
            approval_request.id,
            approval_request.request_status,
            approval_request.quantity,
            approval_request.overtime_disable_auto_checkout,
            attendance.check_in,
            attendance.overtime_authorization_deadline,
            sorted(geo_information.keys()) if geo_information else [],
        )
        return attendance

    def _check_overtime_gate_before_check_in(self):
        """Check-in is always allowed (before or after overtime approval).

        Extra hours are validated when the manager approves an overtime request,
        whether the employee applied before or after working that day.
        """
        self.ensure_one()
        return False

    def _apply_authorized_check_out(self, attendance, action_date, geo_information):
        self.ensure_one()
        check_out_date = action_date
        if (
            attendance.overtime_authorization_deadline
            and not attendance.overtime_authorization_request_id.overtime_disable_auto_checkout
        ):
            check_out_date = min(action_date, attendance.overtime_authorization_deadline)
        _logger.warning(
            "[PortalOTDebug] authorized_check_out_prepare employee_id=%s attendance_id=%s request_id=%s "
            "action_date=%s check_in=%s deadline=%s disable_auto_checkout=%s final_check_out=%s current_worked_hours=%s geo_keys=%s",
            self.id,
            attendance.id,
            attendance.overtime_authorization_request_id.id,
            action_date,
            attendance.check_in,
            attendance.overtime_authorization_deadline,
            attendance.overtime_authorization_request_id.overtime_disable_auto_checkout,
            check_out_date,
            attendance.worked_hours,
            sorted(geo_information.keys()) if geo_information else [],
        )
        if check_out_date <= attendance.check_in:
            _logger.warning(
                "[PortalOTDebug] authorized_check_out_not_after_check_in employee_id=%s attendance_id=%s "
                "request_id=%s check_in=%s final_check_out=%s deadline=%s disable_auto_checkout=%s",
                self.id,
                attendance.id,
                attendance.overtime_authorization_request_id.id,
                attendance.check_in,
                check_out_date,
                attendance.overtime_authorization_deadline,
                attendance.overtime_authorization_request_id.overtime_disable_auto_checkout,
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
            "[PortalOTDebug] authorized_check_out_done employee_id=%s attendance_id=%s request_id=%s "
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

        # Enforce geofence restriction for both check-in and check-out
        self._check_portal_geo_restriction(geo_information=geo_information)

        if self.attendance_state != 'checked_in':
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
