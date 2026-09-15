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
        """Hours used to convert hour-based balance to 'equivalent days' on the Time Off card.
        Always returns standard 8.0 hours per day.
        """
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
                continue

            for _name, info, _requires, lt_id in rows:
                leave_type = self.browse(lt_id) if lt_id else None
                lt_name = (leave_type.name if leave_type else _name or '').lower()
                
                if 'extra' in lt_name or 'إضافي' in lt_name or 'overtime' in lt_name:
                    total_ot_hours = getattr(employee, 'total_overtime', 0.0) or getattr(employee, 'total_extra_hours', 0.0)
                    if not total_ot_hours and 'hr.leave.allocation' in self.env:
                        allocs = self.env['hr.leave.allocation'].sudo().search([
                            ('employee_id', '=', employee.id),
                            ('holiday_status_id', '=', lt_id),
                            ('state', '=', 'validate')
                        ])
                        total_ot_hours = sum(
                            getattr(a, 'number_of_hours_display', 0.0) or (a.number_of_days * 9.4468)
                            for a in allocs
                        )
                    
                    if total_ot_hours > 0.001:
                        equiv_days = round(total_ot_hours / 8.0, 2)
                        info["virtual_remaining_leaves"] = equiv_days
                        info["max_leaves"] = equiv_days
                        info["hours_per_day"] = 8.0
                else:
                    hours_per_day = self._get_dashboard_hours_per_day(employee, ref_date)
                    if hours_per_day:
                        info["hours_per_day"] = round(float(hours_per_day), 2)
        return allocation_data
