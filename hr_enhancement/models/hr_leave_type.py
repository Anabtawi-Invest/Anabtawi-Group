# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

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
                    "hr_enhancement TimeOff: no allocation rows employee_id=%s ref_date=%s",
                    getattr(employee, "id", None),
                    ref_date,
                )
                continue
            hours_per_day = employee._get_hours_per_day(ref_date)
            _logger.debug(
                "hr_enhancement TimeOff: employee_id=%s ref_date=%s _get_hours_per_day=%s rows=%s",
                employee.id,
                ref_date,
                hours_per_day,
                len(rows),
            )
            if not hours_per_day:
                _logger.warning(
                    "hr_enhancement TimeOff: hours_per_day is falsy for employee_id=%s; skip injecting hours_per_day",
                    employee.id,
                )
                continue
            for _name, info, _requires, lt_id in rows:
                if info.get("request_unit") == "hour":
                    info["hours_per_day"] = round(float(hours_per_day), 2)
                    _logger.debug(
                        "hr_enhancement TimeOff: leave_type_id=%s virtual_remaining=%s hours_per_day=%s (in payload)",
                        lt_id,
                        info.get("virtual_remaining_leaves"),
                        info["hours_per_day"],
                    )
        return allocation_data
