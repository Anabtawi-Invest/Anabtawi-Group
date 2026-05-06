# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import fields, models

_logger = logging.getLogger(__name__)

# Fixed divisor for dashboard "equivalent days" display (hours → days).
AE_TIME_OFF_DASHBOARD_HOURS_PER_DAY = 8.0


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    def _get_dashboard_hours_per_day(self, employee, ref_date):
        """Dashboard only: convert hour balance to days as hours ÷ 8 (fixed, not calendar)."""
        return AE_TIME_OFF_DASHBOARD_HOURS_PER_DAY

    def get_allocation_data(self, employees, target_date=None):
        allocation_data = super().get_allocation_data(employees, target_date)

        ref_date = target_date
        if ref_date and isinstance(ref_date, str):
            ref_date = datetime.fromisoformat(ref_date).date()
        elif ref_date and isinstance(ref_date, datetime):
            ref_date = ref_date.date()
        elif not ref_date:
            ref_date = fields.Date.today()

        for employee in employees:
            rows = allocation_data.get(employee)
            if not rows:
                _logger.debug(
                    "hr_health_insurance TimeOff: no allocation rows employee_id=%s ref_date=%s",
                    getattr(employee, "id", None),
                    ref_date,
                )
                continue
            hours_per_day = self._get_dashboard_hours_per_day(employee, ref_date)
            _logger.debug(
                "hr_health_insurance TimeOff: employee_id=%s ref_date=%s dashboard_hours_per_day=%s rows=%s",
                employee.id,
                ref_date,
                hours_per_day,
                len(rows),
            )
            for _name, info, _requires, lt_id in rows:
                if info.get("request_unit") == "hour":
                    info["hours_per_day"] = round(float(hours_per_day), 2)
                    _logger.debug(
                        "hr_health_insurance TimeOff: leave_type_id=%s virtual_remaining=%s hours_per_day=%s (in payload)",
                        lt_id,
                        info.get("virtual_remaining_leaves"),
                        info["hours_per_day"],
                    )
        return allocation_data
