import datetime
from collections import defaultdict
from odoo import models, api

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_reconciled_attendance_variance(self):
        """
        Calculates daily OT (>8h) and daily Undertime (<8h) with an auto 1h break deduction
        for shifts >= 6 hours, then offsets undertime directly against overtime.
        """
        self.ensure_one()
        
        # 1. Fetch attendance records in payslip date window
        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', datetime.datetime.combine(self.date_from, datetime.time.min)),
            ('check_in', '<=', datetime.datetime.combine(self.date_to, datetime.time.max))
        ])

        # 2. Group raw check-in hours by date
        daily_hours = defaultdict(float)
        for att in attendances:
            daily_hours[att.check_in.date()] += att.worked_hours

        total_ot = 0.0
        total_undertime = 0.0
        standard_target = 8.0

        # 3. Apply break rule and compute daily deviation
        for att_date, raw_hrs in daily_hours.items():
            if raw_hrs >= 6.0:
                net_hrs = max(0.0, raw_hrs - 1.0)
            elif raw_hrs > 4.0:
                net_hrs = raw_hrs - 0.5
            else:
                net_hrs = raw_hrs

            if net_hrs > standard_target:
                total_ot += (net_hrs - standard_target)
            elif net_hrs < standard_target:
                total_undertime += (standard_target - net_hrs)

        # 4. Direct Reconciliation: Deduct undertime from overtime pool
        net_variance = total_ot - total_undertime

        return {
            'total_ot': total_ot,
            'total_undertime': total_undertime,
            'net_variance': net_variance  # >0 = Remaining OT, <0 = Excess Undertime
        }
