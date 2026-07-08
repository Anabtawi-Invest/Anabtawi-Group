# -*- coding: utf-8 -*-

import logging
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

    def _get_portal_geofence_company(self):
        self.ensure_one()
        company = self.company_id
        if not company or self.allow_remote_attendance or not company.attendance_geo_enforce:
            return self.env['res.company']
        return company

    def _is_portal_geo_tracking_required(self):
        self.ensure_one()
        company = self._get_portal_geofence_company()
        return bool(company and company._get_valid_attendance_geofence_locations())

    def _check_portal_geo_restriction(self, geo_information=None):
        self.ensure_one()
        # Restrict only check-in; check-out remains unchanged.
        company = self._get_portal_geofence_company()
        if not company:
            return

        locations = company._get_valid_attendance_geofence_locations()
        if not locations:
            raise UserError(_(
                "تم تفعيل نطاق موقع الشركة، لكن لا توجد مواقع شركة مضبوطة بإحداثيات ونطاق صالح."
            ))

        payload = geo_information or {}
        employee_lat = self._safe_float(payload.get('latitude'))
        employee_lon = self._safe_float(payload.get('longitude'))
        if employee_lat is None or employee_lon is None:
            raise UserError(_(
                "تعذر التحقق من موقعك. يرجى تفعيل إذن الموقع ثم المحاولة مرة أخرى."
            ))

        is_within, distance_m, radius_m = company._is_within_attendance_geofence(
            employee_lat, employee_lon
        )
        if not is_within:
            raise UserError(_(
                "تم رفض تسجيل الحضور: أنت خارج جميع مواقع الشركة المسموحة. "
                "أقرب موقع على بعد %.0f متر، والنطاق المسموح %.0f متر."
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
