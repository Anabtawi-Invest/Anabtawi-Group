# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

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
