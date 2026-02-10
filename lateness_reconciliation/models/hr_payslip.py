from odoo import models, fields, api, _
from datetime import timedelta


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Flag to prevent double processing
    lateness_reconciled = fields.Boolean(
        string="Lateness Reconciled",
        default=False,
        help="Indicates whether lateness has already been processed for this payslip."
    )

    # Needed for list view – MUST exist
    lateness_hours = fields.Float(
        string="Lateness Hours",
        compute="_compute_lateness_hours",
        store=True,
        help="Total lateness hours from work entries."
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_lateness_hours(self):
        WorkEntry = self.env['hr.work.entry']
        for slip in self:
            if slip.employee_id and slip.date_from and slip.date_to:
                entries = WorkEntry.search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date_start', '>=', slip.date_from),
                    ('date_stop', '<=', slip.date_to),
                    ('work_entry_type_id.code', '=', 'LATE'),
                ])
                slip.lateness_hours = sum(e.duration for e in entries)
            else:
                slip.lateness_hours = 0.0

    def action_reconcile_lateness(self):
        """
        Odoo 19 safe lateness reconciliation:
        1. Add OT to bank (OTW / OTR / PHO)
        2. Use OT bank
        3. Use Annual Leave
        4. Remaining lateness is unpaid
        """

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

            employee = slip.employee_id
            period_start = slip.date_from
            period_end = slip.date_to

            # ─────────────────────────────
            # 1️⃣ ADD OT TO BANK
            # ─────────────────────────────
            ot_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', period_start),
                ('date_stop', '<=', period_end),
                ('work_entry_type_id.code', 'in', list(OT_MULTIPLIERS.keys())),
            ])

            ot_earned = 0.0
            for entry in ot_entries:
                multiplier = OT_MULTIPLIERS.get(entry.work_entry_type_id.code, 1.0)
                ot_earned += entry.duration * multiplier

            if ot_earned:
                employee.ot_hours_bank += ot_earned

            # ─────────────────────────────
            # 2️⃣ TOTAL LATENESS
            # ─────────────────────────────
            lateness_entries = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '>=', period_start),
                ('date_stop', '<=', period_end),
                ('work_entry_type_id.code', '=', 'LATE'),
            ])

            total_lateness = sum(e.duration for e in lateness_entries)
            remaining = total_lateness

            # ─────────────────────────────
            # 3️⃣ USE OT BANK
            # ─────────────────────────────
            ot_used = 0.0
            if remaining > 0 and employee.ot_hours_bank and AttendanceType:
                ot_used = min(employee.ot_hours_bank, remaining)

                WorkEntry.create({
                    'name': 'Lateness Compensation (OT)',
                    'employee_id': employee.id,
                    'work_entry_type_id': AttendanceType.id,
                    'date_start': period_start,
                    'date_stop': period_start + timedelta(hours=ot_used),
                    'duration': ot_used,
                    'state': 'draft',
                })

                employee.ot_hours_bank -= ot_used
                remaining -= ot_used

            # ─────────────────────────────
            # 4️⃣ USE ANNUAL LEAVE
            # ─────────────────────────────
            leave_used = 0.0
            if remaining > 0 and LeaveType and employee.leaves_count:
                leave_hours_available = employee.leaves_count * 8
                leave_used = min(leave_hours_available, remaining)

                leave = Leave.create({
                    'name': 'Lateness Reconciliation',
                    'employee_id': employee.id,
                    'holiday_status_id': LeaveType.id,
                    'request_date_from': period_start,
                    'request_date_to': period_start + timedelta(hours=leave_used),
                    'number_of_days': leave_used / 8,
                    'state': 'confirm',
                })
                leave.action_approve()
                remaining -= leave_used

            # ─────────────────────────────
            # 5️⃣ FINALIZE
            # ─────────────────────────────
            slip.lateness_reconciled = True
            slip.message_post(body=_(
                "<b>Lateness Reconciliation Completed</b><br/>"
                f"Total Lateness: <b>{total_lateness:.2f} h</b><br/>"
                f"OT Used: <b>{ot_used:.2f} h</b><br/>"
                f"Leave Used: <b>{leave_used:.2f} h</b><br/>"
                f"Unpaid: <b>{remaining:.2f} h</b>"
            ))

        return True
