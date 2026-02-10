from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_reconcile_lateness(self):
        """
        Update OT bank based on work entry codes, then reconcile lateness using:
        1. OT bank (OTW, OTR, PHO)
        2. Annual Leave
        3. Remaining lateness is unpaid (via payroll rules)
        """

        WorkEntry = self.env['hr.work.entry']
        Leave = self.env['hr.leave']
        AttendanceType = self.env.ref('hr_work_entry.work_entry_type_attendance', raise_if_not_found=False)
        LeaveType = self.env['hr.leave.type'].search([('name', 'ilike', 'Annual')], limit=1)

        # Overtime type codes and their multipliers
        OT_MULTIPLIERS = {
            'OTW': 1.25,  # Weekday OT
            'OTR': 1.5,   # Weekend OT
            'PHO': 1.5,   # Public Holiday OT
        }

        for slip in self:
            employee = slip.employee_id
            period_start = slip.date_from
            period_end = slip.date_to

            # === STEP 1: Add OT to Bank ===
            ot_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', period_start),
                ('date_stop', '<=', period_end),
                ('work_entry_type_id.code', 'in', list(OT_MULTIPLIERS.keys()))
            ])

            total_ot_earned = 0.0
            for entry in ot_entries:
                code = entry.work_entry_type_id.code
                multiplier = OT_MULTIPLIERS.get(code, 1.0)
                total_ot_earned += entry.duration * multiplier

            if total_ot_earned > 0:
                employee.ot_hours_bank += total_ot_earned

            # === STEP 2: Get Lateness Work Entries ===
            lateness_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', period_start),
                ('date_stop', '<=', period_end),
                ('work_entry_type_id.code', '=', 'LATE')
            ])

            total_lateness = sum(e.duration for e in lateness_entries)
            hours_to_resolve = total_lateness

            # === STEP 3: Use OT Bank to Resolve Lateness ===
            ot_bank = employee.ot_hours_bank or 0.0
            if ot_bank > 0 and AttendanceType:
                use_ot = min(ot_bank, hours_to_resolve)
                WorkEntry.create({
                    'name': 'Lateness Compensation (OT)',
                    'employee_id': employee.id,
                    'work_entry_type_id': AttendanceType.id,
                    'date_start': period_start,
                    'date_stop': period_start + timedelta(hours=use_ot),
                    'duration': use_ot,
                    'state': 'draft',
                })
                employee.ot_hours_bank -= use_ot
                hours_to_resolve -= use_ot

            # === STEP 4: Use Annual Leave if OT not enough ===
            leave_days = employee.leaves_count or 0.0
            if hours_to_resolve > 0 and leave_days > 0 and LeaveType:
                use_leave_hours = min(leave_days * 8, hours_to_resolve)
                leave = Leave.create({
                    'name': 'Lateness Reconciliation',
                    'employee_id': employee.id,
                    'holiday_status_id': LeaveType.id,
                    'request_date_from': period_start,
                    'request_date_to': period_start + timedelta(hours=use_leave_hours),
                    'number_of_days': use_leave_hours / 8.0,
                    'state': 'confirm',
                })
                leave.action_approve()
                hours_to_resolve -= use_leave_hours

            # Remaining lateness is unpaid — handled by payslip rules

        return True
