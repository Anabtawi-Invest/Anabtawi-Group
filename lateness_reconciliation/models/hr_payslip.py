# -*- coding: utf-8 -*-
##############################################################################
# Lateness Reconciliation - Odoo 19 Online compatible
#
# Confirmed from your database:
# - hr.work.entry does NOT have date_start/date_stop
# - hr.work.entry uses:
#     - date (date)
#     - duration (float)
#
# This file provides:
# - Computed lateness_hours (based on work entries)
# - Single payslip reconciliation action (action_reconcile_lateness)
# - Bulk reconciliation action on pay run (action_bulk_reconcile_lateness)
#
# Notes for Online:
# - No external imports (datetime, logging, etc.)
# - Defensive try/except around leave creation/approval so payroll never crashes
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ot_hours_bank = fields.Float(
        string="OT Hours Bank",
        default=0.0,
        help="Accumulated overtime hours available to compensate lateness."
    )


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    lateness_reconciled = fields.Boolean(
        string="Lateness Reconciled",
        default=False,
        help="Checked when lateness reconciliation has been performed for this payslip."
    )

    lateness_hours = fields.Float(
        string="Lateness Hours",
        compute="_compute_lateness_hours",
        store=True,
        help="Total lateness hours from work entries in the payslip period."
    )

    ot_used = fields.Float(
        string="OT Used",
        readonly=True,
        help="OT hours used from the employee OT bank to compensate lateness."
    )

    leave_used = fields.Float(
        string="Leave Used",
        readonly=True,
        help="Leave hours used to compensate lateness."
    )

    unreconciled_lateness = fields.Float(
        string="Unreconciled Lateness",
        readonly=True,
        help="Remaining lateness hours not compensated by OT bank or leave."
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_lateness_hours(self):
        """
        Compute lateness hours from hr.work.entry using Odoo 19 Online fields:
        - date (date)
        - duration (float)

        IMPORTANT:
        - Your database does not have date_start/date_stop, so we must not use them.
        """
        WorkEntry = self.env['hr.work.entry']

        for slip in self:
            total_lateness = 0.0

            # Safe fallbacks
            if not slip.employee_id or not slip.date_from or not slip.date_to:
                slip.lateness_hours = 0.0
                continue

            # If your lateness type code is not "LATE", change it here.
            lateness_entries = WorkEntry.search([
                ('employee_id', '=', slip.employee_id.id),
                ('date', '>=', slip.date_from),
                ('date', '<=', slip.date_to),
                ('work_entry_type_id.code', '=', 'LATE'),
            ])

            for entry in lateness_entries:
                total_lateness += (entry.duration or 0.0)

            slip.lateness_hours = total_lateness

    def _lateness_reconcile_for_slip(self):
        """
        Internal helper to reconcile lateness for each slip safely.
        Returns a dict of results so bulk action can summarize if needed.
        """
        self.ensure_one()

        WorkEntry = self.env['hr.work.entry']
        Leave = self.env['hr.leave']

        # If your annual leave type name is different, adjust the search.
        LeaveType = self.env['hr.leave.type'].search([('name', 'ilike', 'Annual')], limit=1)

        # Overtime multipliers (adjust codes to match your work entry types)
        OT_MULTIPLIERS = {
            'OTW': 1.25,
            'OTR': 1.5,
            'PHO': 1.5,
        }

        slip = self

        # Validation (kept strict to avoid reconciling wrong slips)
        if not slip.employee_id or not slip.date_from or not slip.date_to:
            raise UserError(_("Please set Employee, Date From, and Date To before reconciling lateness."))

        if slip.state != 'draft':
            raise UserError(_("Lateness can only be reconciled while the payslip is in Draft state."))

        if slip.lateness_reconciled:
            # Safe idempotency
            return {
                'total_lateness': slip.lateness_hours or 0.0,
                'ot_earned': 0.0,
                'ot_used': slip.ot_used or 0.0,
                'leave_used': slip.leave_used or 0.0,
                'remaining': slip.unreconciled_lateness or 0.0,
                'already_reconciled': True,
            }

        employee = slip.employee_id

        # ---- 1) Add overtime earned in the payslip period to OT bank ----
        ot_entries = WorkEntry.search([
            ('employee_id', '=', employee.id),
            ('date', '>=', slip.date_from),
            ('date', '<=', slip.date_to),
            ('work_entry_type_id.code', 'in', list(OT_MULTIPLIERS.keys())),
        ])

        ot_earned = 0.0
        for entry in ot_entries:
            code = entry.work_entry_type_id.code or ''
            multiplier = OT_MULTIPLIERS.get(code, 1.0)
            ot_earned += (entry.duration or 0.0) * multiplier

        if ot_earned:
            employee.write({'ot_hours_bank': (employee.ot_hours_bank or 0.0) + ot_earned})

        # ---- 2) Determine total lateness for the payslip period ----
        # We rely on computed field to avoid duplicate searches, but keep safe fallback.
        total_lateness = slip.lateness_hours or 0.0
        remaining = total_lateness

        # ---- 3) Use OT bank to cover lateness ----
        ot_used = 0.0
        bank = employee.ot_hours_bank or 0.0
        if remaining > 0.0 and bank > 0.0:
            ot_used = min(bank, remaining)
            employee.write({'ot_hours_bank': bank - ot_used})
            remaining -= ot_used

        # ---- 4) Use Annual Leave (optional, safe) ----
        # Assumption: 8 hours = 1 day (change if your company uses a different standard)
        leave_used = 0.0
        leave_created = False

        if remaining > 0.0 and LeaveType:
            # Some databases have leaves_count; keep safe if not present
            available_days = getattr(employee, 'leaves_count', 0.0) or 0.0
            available_hours = available_days * 8.0

            if available_hours > 0.0:
                leave_hours = min(available_hours, remaining)

                # Create leave on slip.date_from (simple & robust)
                leave_vals = {
                    'name': 'Lateness Reconciliation',
                    'employee_id': employee.id,
                    'holiday_status_id': LeaveType.id,
                    'request_date_from': slip.date_from,
                    'request_date_to': slip.date_from,
                    'number_of_days': leave_hours / 8.0,
                }

                try:
                    leave = Leave.create(leave_vals)
                    leave_created = True
                    # Approvals may be required; do not crash if not allowed
                    try:
                        leave.action_approve()
                    except Exception:
                        pass
                    leave_used = leave_hours
                    remaining -= leave_hours
                except Exception:
                    # If leave creation fails due to config (units/hours/approvals),
                    # we do NOT crash payroll: we just skip leave compensation.
                    leave_created = False
                    leave_used = 0.0

        # ---- 5) Store results on payslip ----
        slip.write({
            'lateness_reconciled': True,
            'ot_used': ot_used,
            'leave_used': leave_used,
            'unreconciled_lateness': remaining,
        })

        # Optional chatter message (safe)
        slip.message_post(body=_(
            "<b>Lateness Reconciliation Completed</b><br/>"
            "Total Lateness: <b>%.2f h</b><br/>"
            "OT Earned Added to Bank: <b>%.2f h</b><br/>"
            "OT Used: <b>%.2f h</b><br/>"
            "Leave Used: <b>%.2f h</b><br/>"
            "Unreconciled: <b>%.2f h</b><br/>"
            "Leave Created: <b>%s</b>"
        ) % (total_lateness, ot_earned, ot_used, leave_used, remaining, 'Yes' if leave_created else 'No'))

        return {
            'total_lateness': total_lateness,
            'ot_earned': ot_earned,
            'ot_used': ot_used,
            'leave_used': leave_used,
            'remaining': remaining,
            'already_reconciled': False,
        }

    def action_reconcile_lateness(self):
        """
        Single payslip button action.
        """
        for slip in self:
            slip._lateness_reconcile_for_slip()
        return True


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_bulk_reconcile_lateness(self):
        """
        Bulk reconcile lateness for ALL draft payslips in this pay run.
        Designed to be triggered from a button on the Pay Run form.
        """
        for run in self:
            if not run.slip_ids:
                raise UserError(_("No payslips found in this pay run."))

            draft_slips = run.slip_ids.filtered(lambda s: s.state == 'draft')
            if not draft_slips:
                raise UserError(_("No draft payslips to reconcile in this pay run."))

            # Reconcile each slip safely
            for slip in draft_slips:
                slip._lateness_reconcile_for_slip()

        return True
