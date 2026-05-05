# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import fields, models
from odoo.addons.resource.models.utils import HOURS_PER_DAY

_logger = logging.getLogger(__name__)

# Odoo's _get_hours_per_day returns 24 when there is no working calendar (fully flexible placeholder).
_FILLER_FULL_DAY_HOURS = 24


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    def _get_dashboard_hours_per_day(self, employee, ref_date):
        """Hours used only to convert hour-based balance to 'equivalent days' on the Time Off card.

        When Odoo has no calendar it uses 24h as a technical placeholder; for display we prefer
        the employee/company calendar or the standard 8h default (same idea as other hr_holidays UIs).
        """
        hpd = employee._get_hours_per_day(ref_date)
        if hpd and hpd != _FILLER_FULL_DAY_HOURS:
            return float(hpd)
        cal_hpd = employee.resource_calendar_id.hours_per_day
        if cal_hpd:
            return float(cal_hpd)
        company_cal = employee.company_id.resource_calendar_id
        if company_cal and company_cal.hours_per_day:
            return float(company_cal.hours_per_day)
        if hpd == _FILLER_FULL_DAY_HOURS:
            _logger.debug(
                "hr_enhancement TimeOff: employee_id=%s _get_hours_per_day=24 (no calendar); "
                "using HOURS_PER_DAY=%s for day equivalent display",
                employee.id,
                HOURS_PER_DAY,
            )
        return float(HOURS_PER_DAY)

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
            hours_per_day = self._get_dashboard_hours_per_day(employee, ref_date)
            _logger.debug(
                "hr_enhancement TimeOff: employee_id=%s ref_date=%s dashboard_hours_per_day=%s rows=%s",
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
