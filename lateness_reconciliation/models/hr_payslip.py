from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    lateness_reconciled = fields.Boolean(
        string="Lateness Reconciled",
        default=False,
        help="Indicates whether lateness has already been processed for this payslip."
    )

    def action_reconcile_lateness(self):
        """
        Update OT bank based on work entry codes, then reconcile lateness using:
        1. OT bank
        2. Annual Leave
        3. Remaining lateness is unpaid
        Also tracks reconciliation and prevents duplicate processing.
        """

        WorkEntry = self.env['hr.work.entry']
        Leave = self.env['hr.leave']
        AttendanceType = self.env.ref('hr_work_entry.work_entry_type_attendance', raise_if_not_found=False)
        LeaveType = self.env['hr.leave.type'].search([('name', 'ilike', 'Annual')], limit=1)

        OT_MULTIPLIERS = {
            'OTW': 1.25,
            'OTR': 1.5,
            'PHO': 1.5,
        }

        for slip in self:
            if slip.lateness_reconciled:
                continue  # Skip if already processed

            employee = slip.employee_id
            period_start = slip.date_from
            period_end = slip.date_to

            # === Step 1: Add OT to Bank ===
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

            # === Step 2: Find Lateness ===
            lateness_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', period_start),
                ('date_stop', '<=', period_end),
                ('work_entry_type_id.code', '=', 'LATE')
            ])
            total_lateness = sum(e.duration for e in lateness_entries)
            hours_to_resolve = total_lateness

            # === Step 3: Use OT ===
            ot_used = 0.0
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
                ot_used = use_ot

            # === Step 4: Use Leave ===
            leave_used = 0.0
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
                leave_used = use_leave_hours

            unpaid = max(0.0, hours_to_resolve)

            # === Step 5: Mark and Log ===
            slip.lateness_reconciled = True
            slip.message_post(body=_(
                "<b>Lateness Reconciliation Completed</b><br/>"
                f"Total Lateness: <b>{total_lateness:.2f}h</b><br/>"
                f"Resolved with OT: <b>{ot_used:.2f}h</b><br/>"
                f"Resolved with Leave: <b>{leave_used:.2f}h</b><br/>"
                f"Unpaid (to be deducted): <b>{unpaid:.2f}h</b>"
            ))

        return True
