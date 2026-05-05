# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import fields, models


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
                continue
            hours_per_day = employee._get_hours_per_day(ref_date)
            if not hours_per_day:
                continue
            for _, info, _, _ in rows:
                if info.get("request_unit") == "hour":
                    info["hours_per_day"] = round(float(hours_per_day), 2)
        return allocation_data
