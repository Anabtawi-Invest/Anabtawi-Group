from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_reconcile_lateness(self):
        WorkEntry = self.env['hr.work.entry']
        Leave = self.env['hr.leave']
        AttendanceType = self.env.ref('hr_work_entry.work_entry_type_attendance', raise_if_not_found=False)
        LeaveType = self.env['hr.leave.type'].search([('name', 'ilike', 'Annual')], limit=1)

        for slip in self:
            employee = slip.employee_id
            ot_bank = employee.ot_hours_bank or 0.0
            leave_days = employee.leaves_count or 0.0
            period_start = slip.date_from
            period_end = slip.date_to

            # Get lateness work entries
            lateness_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', period_start),
                ('date_stop', '<=', period_end),
                ('work_entry_type_id.name', 'ilike', 'late')
            ])

            total_lateness = sum(e.duration for e in lateness_entries)
            hours_to_resolve = total_lateness

            # Offset with OT bank
            if ot_bank > 0:
                use_ot = min(ot_bank, hours_to_resolve)
                WorkEntry.create({
                    'name': 'Lateness Compensation - OT',
                    'employee_id': employee.id,
                    'work_entry_type_id': AttendanceType.id,
                    'date_start': slip.date_from,
                    'date_stop': slip.date_from + timedelta(hours=use_ot),
                    'duration': use_ot,
                    'state': 'draft',
                })
                hours_to_resolve -= use_ot
                employee.ot_hours_bank -= use_ot

            # Offset with leave
            if hours_to_resolve > 0 and leave_days > 0 and LeaveType:
                use_leave_hours = min(leave_days * 8, hours_to_resolve)
                leave = Leave.create({
                    'name': 'Lateness Reconciliation',
                    'employee_id': employee.id,
                    'holiday_status_id': LeaveType.id,
                    'request_date_from': slip.date_from,
                    'request_date_to': slip.date_from + timedelta(hours=use_leave_hours),
                    'number_of_days': use_leave_hours / 8.0,
                    'state': 'confirm',
                })
                leave.action_approve()
                hours_to_resolve -= use_leave_hours

            # Remaining lateness will be deducted from net salary automatically