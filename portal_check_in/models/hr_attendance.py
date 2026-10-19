# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def write(self, vals):
        check_out_raw = vals.get("check_out") if "check_out" in vals else None
        parsed_check_out = fields.Datetime.to_datetime(check_out_raw) if check_out_raw else None
        if "check_out" in vals:
            for attendance in self:
                if not attendance.check_in or not parsed_check_out:
                    continue
                if parsed_check_out <= attendance.check_in:
                    _logger.warning(
                        "[PortalOTDebug] suspicious_check_out_write_before_save attendance_id=%s employee_id=%s "
                        "check_in=%s incoming_check_out=%s out_mode_in_vals=%s existing_out_mode=%s "
                        "request_id=%s request_status=%s request_qty=%s request_disable_auto_checkout=%s deadline=%s context=%s",
                        attendance.id,
                        attendance.employee_id.id,
                        attendance.check_in,
                        parsed_check_out,
                        vals.get("out_mode"),
                        attendance.out_mode,
                        attendance.overtime_authorization_request_id.id if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_request_id.request_status if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_request_id.quantity if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_request_id.overtime_disable_auto_checkout
                        if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_deadline,
                        {
                            "uid": self.env.uid,
                            "is_cron": bool(self.env.context.get("cron_id")),
                            "from_portal_check_in": self.env.context.get("from_portal_check_in"),
                            "active_model": self.env.context.get("active_model"),
                            "active_id": self.env.context.get("active_id"),
                        },
                    )

        result = super().write(vals)

        if "check_out" in vals:
            for attendance in self.filtered("check_out"):
                if attendance.check_in and attendance.check_out <= attendance.check_in:
                    _logger.warning(
                        "[PortalOTDebug] suspicious_check_out_persisted attendance_id=%s employee_id=%s "
                        "check_in=%s persisted_check_out=%s out_mode=%s request_id=%s request_status=%s "
                        "request_qty=%s request_disable_auto_checkout=%s deadline=%s",
                        attendance.id,
                        attendance.employee_id.id,
                        attendance.check_in,
                        attendance.check_out,
                        attendance.out_mode,
                        attendance.overtime_authorization_request_id.id if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_request_id.request_status if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_request_id.quantity if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_request_id.overtime_disable_auto_checkout
                        if attendance.overtime_authorization_request_id else False,
                        attendance.overtime_authorization_deadline,
                    )
        return result

    def _get_portal_approved_overtime_hours(self):
        """Return approved overtime hours to extend auto check-out threshold."""
        self.ensure_one()
        if not self.employee_id or not self.check_in:
            return 0.0

        # If attendance is explicitly linked to an overtime request, prefer it.
        linked_request = getattr(self, "overtime_authorization_request_id", False)
        if linked_request and linked_request.request_status == "approved":
            return max(linked_request.quantity or 0.0, 0.0)

        approval_model = self.env["approval.request"]
        required_fields = {
            "is_overtime_category",
            "overtime_employee_id",
            "request_status",
            "overtime_date_from",
            "overtime_date_to",
            "quantity",
        }
        if not required_fields.issubset(set(approval_model._fields)):
            return 0.0

        employee_tz = pytz.timezone(self.employee_id.tz or "UTC")
        target_date = pytz.utc.localize(self.check_in).astimezone(employee_tz).date()
        approved_requests = approval_model.search([
            ("is_overtime_category", "=", True),
            ("overtime_employee_id", "=", self.employee_id.id),
            ("request_status", "=", "approved"),
            ("overtime_date_from", "<=", target_date),
            ("overtime_date_to", ">=", target_date),
        ])
        overtime_hours = sum(max(req.quantity or 0.0, 0.0) for req in approved_requests)
        return overtime_hours

    def _has_portal_open_overtime_request(self):
        """Submitted/Pending overtime request blocks auto check-out."""
        self.ensure_one()
        if not self.employee_id or not self.check_in:
            return False

        approval_model = self.env["approval.request"]
        required_fields = {
            "is_overtime_category",
            "overtime_employee_id",
            "request_status",
            "overtime_date_from",
            "overtime_date_to",
        }
        if not required_fields.issubset(set(approval_model._fields)):
            return False

        employee_tz = pytz.timezone(self.employee_id.tz or "UTC")
        target_date = pytz.utc.localize(self.check_in).astimezone(employee_tz).date()
        open_request = approval_model.search(
            [
                ("is_overtime_category", "=", True),
                ("overtime_employee_id", "=", self.employee_id.id),
                ("request_status", "in", ("new", "pending")),
                ("overtime_date_from", "<=", target_date),
                ("overtime_date_to", ">=", target_date),
            ],
            limit=1,
        )
        return bool(open_request)

    def _get_portal_shift_end_with_grace_utc(self, grace_minutes=15):
        self.ensure_one()
        if not self.employee_id or not self.check_in:
            return False

        employee = self.employee_id
        employee_tz = pytz.timezone(employee.tz or "UTC")
        check_in_local = pytz.utc.localize(self.check_in).astimezone(employee_tz)
        day_start_local = check_in_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_local = day_start_local + timedelta(days=1)

        intervals = employee._get_expected_attendances(day_start_local, day_end_local)
        candidate_ends = []
        for start, end, _meta in intervals:
            if end <= check_in_local:
                continue
            if start.date() == check_in_local.date() or end.date() == check_in_local.date():
                candidate_ends.append(end)

        if not candidate_ends:
            return False

        shift_end_local = max(candidate_ends)
        approved_overtime_hours = self._get_portal_approved_overtime_hours()
        if approved_overtime_hours > 0:
            shift_end_local += timedelta(hours=approved_overtime_hours)
            _logger.info(
                "portal_check_in auto checkout threshold extended by approved overtime: "
                "attendance_id=%s employee_id=%s overtime_hours=%s extended_shift_end_local=%s",
                self.id,
                self.employee_id.id,
                approved_overtime_hours,
                shift_end_local,
            )
        shift_end_with_grace_local = shift_end_local + timedelta(minutes=grace_minutes)
        return shift_end_with_grace_local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _cron_portal_auto_check_out_after_shift(self):
        now_utc = fields.Datetime.now()
        open_attendances = self.search([("check_out", "=", False), ("check_in", "!=", False)])
        if not open_attendances:
            return

        for attendance in open_attendances:
            if attendance._has_portal_open_overtime_request():
                _logger.info(
                    "portal_check_in auto checkout skipped due to open overtime request: "
                    "attendance_id=%s employee_id=%s check_in=%s",
                    attendance.id,
                    attendance.employee_id.id,
                    attendance.check_in,
                )
                continue
            auto_check_out_at = attendance._get_portal_shift_end_with_grace_utc(grace_minutes=15)
            if not auto_check_out_at:
                continue
            if auto_check_out_at <= attendance.check_in:
                continue
            # hr.work.entry enforces a max 24h duration; clamp to avoid cron failures
            # for stale/open attendances or unexpected shift intervals.
            max_allowed_check_out = attendance.check_in + timedelta(hours=23, minutes=59, seconds=59)
            if auto_check_out_at > max_allowed_check_out:
                _logger.warning(
                    "portal_check_in auto checkout clamped to 24h window: attendance_id=%s employee_id=%s "
                    "check_in=%s planned_check_out=%s clamped_check_out=%s",
                    attendance.id,
                    attendance.employee_id.id,
                    attendance.check_in,
                    auto_check_out_at,
                    max_allowed_check_out,
                )
                auto_check_out_at = max_allowed_check_out
            if now_utc < auto_check_out_at:
                continue

            try:
                attendance.write({
                    "check_out": auto_check_out_at,
                    "out_mode": "auto_check_out",
                })
            except ValidationError:
                _logger.exception(
                    "portal_check_in auto checkout failed validation: attendance_id=%s employee_id=%s "
                    "check_in=%s attempted_check_out=%s",
                    attendance.id,
                    attendance.employee_id.id,
                    attendance.check_in,
                    auto_check_out_at,
                )
                continue
            _logger.info(
                "portal_check_in auto checkout applied: attendance_id=%s employee_id=%s check_in=%s check_out=%s",
                attendance.id,
                attendance.employee_id.id,
                attendance.check_in,
                auto_check_out_at,
            )
