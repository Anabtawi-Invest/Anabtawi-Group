# -*- coding: utf-8 -*-
##############################################################################
# Lateness Reconciliation - Odoo 19 Compatible
#
# CONFIRMED FOR YOUR DATABASE:
# - hr.work.entry uses:
#       date (date)
#       duration (float)
# - NO date_start / date_stop
#
# Features:
# - Computes lateness_hours from work entries (code = LATE)
# - Adds OT earned to employee OT bank
# - Uses OT bank first
# - Uses Annual Leave second
# - Stores reconciliation tracking fields
# - Safe against payroll crashes
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError


# ============================================================
# EXTEND EMPLOYEE
# ============================================================

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ot_hours_bank = fields.Float(
        string="OT Hours Bank",
        default=0.0,
        help="Accumulated overtime hours available to compensate lateness."
    )


# ============================================================
# EXTEND PAYSLIP
# ============================================================

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ---------------------------
    # Tracking Fields
    # ---------------------------

    lateness_reconciled = fields.Boolean(
        string="Lateness Reconciled",
        default=False,
        help="Checked once reconciliation is completed."
    )

    lateness_hours = fields.Float(
        string="Lateness Hours",
        compute="_compute_lateness_hours",
        store=True
    )

    ot_used = fields.Float(
        string="OT Used",
        readonly=True
    )

    leave_used = fields.Float(
        string="Leave Used",
        readonly=True
    )

    unreconciled_lateness = fields.Float(
        string="Unreconciled Lateness",
        readonly=True
    )

    # ============================================================
    # COMPUTE LATENESS HOURS
    # ============================================================

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_lateness_hours(self):
        WorkEntry = self.env['hr.work.entry']

        for slip in self:
            slip.lateness_hours = 0.0

            if not slip.employee_id or not slip.date_from or not slip.date_to:
                continue

            entries = WorkEntry.search([
                ('employee_id', '=', slip.employee_id.id),
                ('date', '>=', slip.date_from),
                ('date', '<=', slip.date_to),
                ('work_entry_type_id.code', '=', 'LATE'),
            ])

            total = 0.0
            for entry in entries:
                total += entry.duration or 0.0

            slip.lateness_hours = total

    # ============================================================
    # INTERNAL RECONCILIATION LOGIC
    # ============================================================

    def _lateness_reconcile_for_slip(self):
        self.ensure_one()

        if not self.employee_id or not self.date_from or not self.date_to:
            raise UserError(_("Please define Employee and Payslip period first."))

        if self.state != 'draft':
            raise UserError(_("Payslip must be in Draft state."))

        if self.lateness_reconciled:
            return

        WorkEntry = self.env['hr.work.entry']
        Leave = self.env['hr.leave']

        employee = self.employee_id
        total_lateness = self.lateness_hours or 0.0
        remaining = total_lateness

        # ============================================================
        # 1️⃣ ADD OT EARNED TO BANK
        # ============================================================

        OT_MULTIPLIERS = {
            'OTW': 1.25,
            'OTR': 1.5,
            'PHO': 1.5,
        }

        ot_entries = WorkEntry.search([
            ('employee_id', '=', employee.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('work_entry_type_id.code', 'in', list(OT_MULTIPLIERS.keys())),
        ])

        ot_earned = 0.0
        for entry in ot_entries:
            multiplier = OT_MULTIPLIERS.get(entry.work_entry_type_id.code, 1.0)
            ot_earned += (entry.duration or 0.0) * multiplier

        if ot_earned:
            employee.write({
                'ot_hours_bank': (employee.ot_hours_bank or 0.0) + ot_earned
            })

        # ============================================================
        # 2️⃣ USE OT BANK
        # ============================================================

        ot_used = 0.0
        bank = employee.ot_hours_bank or 0.0

        if remaining > 0 and bank > 0:
            ot_used = min(bank, remaining)
            employee.write({
                'ot_hours_bank': bank - ot_used
            })
            remaining -= ot_used

        # ============================================================
        # 3️⃣ USE ANNUAL LEAVE
        # ============================================================

        leave_used = 0.0
        LeaveType = self.env['hr.leave.type'].search(
            [('name', 'ilike', 'Annual')],
            limit=1
        )

        if remaining > 0 and LeaveType:
            available_days = getattr(employee, 'leaves_count', 0.0) or 0.0
            available_hours = available_days * 8.0

            if available_hours > 0:
                leave_hours = min(available_hours, remaining)

                try:
                    leave = Leave.create({
                        'name': 'Lateness Reconciliation',
                        'employee_id': employee.id,
                        'holiday_status_id': LeaveType.id,
                        'request_date_from': self.date_from,
                        'request_date_to': self.date_from,
                        'number_of_days': leave_hours / 8.0,
                    })

                    try:
                        leave.action_approve()
                    except Exception:
                        pass

                    leave_used = leave_hours
                    remaining -= leave_hours

                except Exception:
                    leave_used = 0.0

        # ============================================================
        # 4️⃣ STORE RESULTS
        # ============================================================

        self.write({
            'lateness_reconciled': True,
            'ot_used': ot_used,
            'leave_used': leave_used,
            'unreconciled_lateness': remaining,
        })

        self.message_post(body=_(
            "<b>Lateness Reconciliation Completed</b><br/>"
            "Total Lateness: <b>%.2f h</b><br/>"
            "OT Earned: <b>%.2f h</b><br/>"
            "OT Used: <b>%.2f h</b><br/>"
            "Leave Used: <b>%.2f h</b><br/>"
            "Remaining (Unpaid): <b>%.2f h</b>"
        ) % (total_lateness, ot_earned, ot_used, leave_used, remaining))

    # ============================================================
    # BUTTON ACTION
    # ============================================================

    def action_reconcile_lateness(self):
        for slip in self:
            slip._lateness_reconcile_for_slip()
        return True


# ============================================================
# EXTEND PAY RUN
# ============================================================

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_bulk_reconcile_lateness(self):
        for run in self:

            draft_slips = run.slip_ids.filtered(lambda s: s.state == 'draft')

            if not draft_slips:
                raise UserError(_("No draft payslips to reconcile."))

            for slip in draft_slips:
                slip._lateness_reconcile_for_slip()

        return True
