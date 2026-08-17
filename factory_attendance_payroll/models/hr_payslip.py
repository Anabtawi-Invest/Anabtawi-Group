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


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def action_generate_test_attendances(self):
        """Generates 1 month of test attendance records for August 2026 for selected employees."""
        import calendar
        Attendance = self.env['hr.attendance']

        for employee in self:
            year, month = 2026, 8
            start_date = datetime.date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_date = datetime.date(year, month, last_day)

            # Clean existing test attendances in this window
            existing = Attendance.search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', datetime.datetime.combine(start_date, datetime.time.min)),
                ('check_in', '<=', datetime.datetime.combine(end_date, datetime.time.max))
            ])
            existing.unlink()

            # Create test attendance entries
            for day in range(1, last_day + 1):
                dt = datetime.date(year, month, day)
                weekday = dt.weekday()
                if weekday == 6:  # Skip Sundays
                    continue

                if weekday in (0, 3):  # Mon, Thu -> 10h shift (Net 9h -> +1h OT)
                    c_in = datetime.datetime.combine(dt, datetime.time(8, 0, 0))
                    c_out = datetime.datetime.combine(dt, datetime.time(18, 0, 0))
                elif weekday == 2:  # Wed -> 7h shift (Net 6h -> -2h UT)
                    c_in = datetime.datetime.combine(dt, datetime.time(8, 0, 0))
                    c_out = datetime.datetime.combine(dt, datetime.time(15, 0, 0))
                else:  # Tue, Fri, Sat -> 9h shift (Net 8h -> 0h variance)
                    c_in = datetime.datetime.combine(dt, datetime.time(8, 0, 0))
                    c_out = datetime.datetime.combine(dt, datetime.time(17, 0, 0))

                Attendance.create({
                    'employee_id': employee.id,
                    'check_in': c_in,
                    'check_out': c_out,
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Test Attendances Generated!',
                'message': f'Full month test attendance records (Aug 2026) have been generated for {len(self)} employee(s).',
                'sticky': False,
            }
        }

