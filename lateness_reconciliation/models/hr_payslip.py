from odoo import models, fields, api, _
from datetime import datetime, time, timedelta


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    lateness_reconciled = fields.Boolean(
        string="Lateness Reconciled",
        default=False
    )

    lateness_hours = fields.Float(
        string="Lateness Hours",
        compute="_compute_lateness_hours",
        store=True
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_lateness_hours(self):
        WorkEntry = self.env['hr.work.entry']

        for slip in self:
            slip.lateness_hours = 0.0

            if not slip.employee_id or not slip.date_from or not slip.date_to:
                continue

            start_dt = datetime.combine(slip.date_from, time.min)
            end_dt = datetime.combine(slip.date_to, time.max)

            entries = WorkEntry.search([
                ('employee_id', '=', slip.employee_id.id),
                ('date_start', '>=', start_dt),
                ('date_stop', '<=', end_dt),
                ('work_entry_type_id.code', '=', 'LATE'),
            ])

            slip.lateness_hours = sum(e.duration for e in entries)

    def action_reconcile_lateness(self):
        WorkEntry = self.env['hr.work.entry']
        Leave = self.env['hr.leave']

        AttendanceType = self.env.ref(
            'hr_work_entry.work_entry_type_attendance',
            raise_if_not_found=False
        )

        LeaveType = self.env['hr.leave.type'].search(
            [('name', 'ilike', 'Annual')],
            limit=1
        )

        OT_MULTIPLIERS = {
            'OTW': 1.25,
            'OTR': 1.5,
            'PHO': 1.5,
        }

        for slip in self:
            if slip.lateness_reconciled:
                continue

            if not slip.employee_id or not slip.date_from or not slip.date_to:
                continue

            employee = slip.employee_id

            start_dt = datetime.combine(slip.date_from, time.min)
            end_dt = datetime.combine(slip.date_to, time.max)

            # 1️⃣ ADD OT TO BANK
            ot_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', start_dt),
                ('date_stop', '<=', end_dt),
                ('work_entry_type_id.code', 'in', list(OT_MULTIPLIERS.keys())),
            ])

            ot_earned = sum(
                entry.duration * OT_MULTIPLIERS.get(entry.work_entry_type_id.code, 1.0)
                for entry in ot_entries
            )

            if ot_earned:
                employee.ot_hours_bank += ot_earned

            # 2️⃣ COLLECT LATENESS
            lateness_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', start_dt),
                ('date_stop', '<=', end_dt),
                ('work_entry_type_id.code', '=', 'LATE'),
            ], order="date_start asc")

            total_lateness = sum(e.duration for e in lateness_entries)
            remaining = total_lateness

            # 3️⃣ USE OT BANK
            ot_used = 0.0
            if remaining > 0 and employee.ot_hours_bank and AttendanceType:
                ot_used = min(employee.ot_hours_bank, remaining)

                WorkEntry.create({
                    'name': 'Lateness Compensation (OT)',
                    'employee_id': employee.id,
                    'work_entry_type_id': AttendanceType.id,
                    'date_start': start_dt,
                    'date_stop': start_dt + timedelta(hours=ot_used),
                    'duration': ot_used,
                    'state': 'draft',
                })

                employee.ot_hours_bank -= ot_used
                remaining -= ot_used

            # 4️⃣ USE LEAVE
            leave_used = 0.0
            if remaining > 0 and LeaveType and employee.leaves_count:
                leave_hours = min(employee.leaves_count * 8, remaining)

                leave = Leave.create({
                    'name': 'Lateness Reconciliation',
                    'employee_id': employee.id,
                    'holiday_status_id': LeaveType.id,
                    'request_date_from': slip.date_from,
                    'request_date_to': slip.date_from,
                    'number_of_days': leave_hours / 8,
                    'state': 'confirm',
                })
                leave.action_approve()

                leave_used = leave_hours
                remaining -= leave_hours

            slip.lateness_reconciled = True

            slip.message_post(body=_(
                "<b>Lateness Reconciliation Completed</b><br/>"
                f"Total Lateness: <b>{total_lateness:.2f} h</b><br/>"
                f"OT Used: <b>{ot_used:.2f} h</b><br/>"
                f"Leave Used: <b>{leave_used:.2f} h</b><br/>"
                f"Unpaid: <b>{remaining:.2f} h</b>"
            ))

        return True
