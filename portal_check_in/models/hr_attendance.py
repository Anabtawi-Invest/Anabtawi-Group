# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _has_submitted_overtime_request(self):
        self.ensure_one()
        if not self.employee_id or not self.check_in:
            return False

        approval_model = self.env["approval.request"]
        if "is_overtime_category" not in approval_model._fields:
            return False

        employee_tz = pytz.timezone(self.employee_id.tz or "UTC")
        check_in_local_date = pytz.utc.localize(self.check_in).astimezone(employee_tz).date()
        domain = [
            ("is_overtime_category", "=", True),
            ("overtime_employee_id", "=", self.employee_id.id),
            ("request_status", "in", ("new", "pending")),
            ("overtime_date_from", "<=", check_in_local_date),
            ("overtime_date_to", ">=", check_in_local_date),
        ]
        return bool(approval_model.search_count(domain))

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
        shift_end_with_grace_local = shift_end_local + timedelta(minutes=grace_minutes)
        return shift_end_with_grace_local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _cron_portal_auto_check_out_after_shift(self):
        now_utc = fields.Datetime.now()
        open_attendances = self.search([("check_out", "=", False), ("check_in", "!=", False)])
        if not open_attendances:
            return

        for attendance in open_attendances:
            auto_check_out_at = attendance._get_portal_shift_end_with_grace_utc(grace_minutes=15)
            if not auto_check_out_at:
                continue
            if auto_check_out_at <= attendance.check_in:
                continue
            if now_utc < auto_check_out_at:
                continue
            if attendance._has_submitted_overtime_request():
                _logger.info(
                    "portal_check_in auto checkout skipped due to submitted overtime request: "
                    "attendance_id=%s employee_id=%s",
                    attendance.id,
                    attendance.employee_id.id,
                )
                continue

            attendance.write({
                "check_out": auto_check_out_at,
                "out_mode": "auto_check_out",
            })
            _logger.info(
                "portal_check_in auto checkout applied: attendance_id=%s employee_id=%s check_in=%s check_out=%s",
                attendance.id,
                attendance.employee_id.id,
                attendance.check_in,
                auto_check_out_at,
            )
# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _has_submitted_overtime_request(self):
        self.ensure_one()
        if not self.employee_id or not self.check_in:
            return False

        approval_model = self.env["approval.request"]
        if "is_overtime_category" not in approval_model._fields:
            return False

        employee_tz = pytz.timezone(self.employee_id.tz or "UTC")
        check_in_local_date = pytz.utc.localize(self.check_in).astimezone(employee_tz).date()
        domain = [
            ("is_overtime_category", "=", True),
            ("overtime_employee_id", "=", self.employee_id.id),
            ("request_status", "in", ("new", "pending")),
            ("overtime_date_from", "<=", check_in_local_date),
            ("overtime_date_to", ">=", check_in_local_date),
        ]
        return bool(approval_model.search_count(domain))

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
        shift_end_with_grace_local = shift_end_local + timedelta(minutes=grace_minutes)
        return shift_end_with_grace_local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _cron_portal_auto_check_out_after_shift(self):
        now_utc = fields.Datetime.now()
        open_attendances = self.search([("check_out", "=", False), ("check_in", "!=", False)])
        if not open_attendances:
            return

        for attendance in open_attendances:
            auto_check_out_at = attendance._get_portal_shift_end_with_grace_utc(grace_minutes=15)
            if not auto_check_out_at:
                continue
            if auto_check_out_at <= attendance.check_in:
                continue
            if now_utc < auto_check_out_at:
                continue
            if attendance._has_submitted_overtime_request():
                _logger.info(
                    "portal_check_in auto checkout skipped due to submitted overtime request: "
                    "attendance_id=%s employee_id=%s",
                    attendance.id,
                    attendance.employee_id.id,
                )
                continue

            attendance.write({
                "check_out": auto_check_out_at,
                "out_mode": "auto_check_out",
            })
            _logger.info(
                "portal_check_in auto checkout applied: attendance_id=%s employee_id=%s check_in=%s check_out=%s",
                attendance.id,
                attendance.employee_id.id,
                attendance.check_in,
                auto_check_out_at,
            )
