# -*- coding: utf-8 -*-
##############################################################################
# Lateness Reconciliation - Odoo 19 Online compatible
#
# Key fixes for Odoo 19 Online:
# - hr.work.entry does NOT have date_start/date_stop in your database
# - Use hr.work.entry.date (date field) + duration (float)
# - Ensure button method action_reconcile_lateness exists (view requires it)
# - Provide fields referenced by XML views (ot_used, leave_used, unreconciled_lateness)
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

            if not slip.employee_id or not slip.date_from or not slip.date_to:
                slip.lateness_hours = 0.0
                continue

            # Work entries in the payslip date range
            lateness_entries = WorkEntry.search([
                ('employee_id', '=', slip.employee_id.id),
                ('date', '>=', slip.date_from),
                ('date', '<=', slip.date_to),
                ('work_entry_type_id.code', '=', 'LATE'),
            ])

            # Sum safely
            for entry in lateness_entries:
                total_lateness += (entry.duration or 0.0)

            slip.lateness_hours = total_lateness

    def action_reconcile_lateness(self):
        """
        Reconcile lateness using:
        1) Add overtime earned in the payslip period to employee OT bank (with multipliers)
        2) Use OT bank to compensate lateness
        3) Use Annual Leave (if available) to compensate remaining lateness
        4) Store results on payslip fields and mark lateness_reconciled

        Notes:
        - Odoo 19 Online hr.work.entry uses date (date), not date_start/date_stop
        - We avoid creating work entries with date_start/date_stop (invalid in your DB)
        - We store reconciliation results on the payslip for payroll rules/reporting
        """
        WorkEntry = self.env['hr.work.entry']
        Leave = self.env['hr.leave']

        # Find an Annual leave type safely (adjust the search if your leave type name differs)
        LeaveType = self.env['hr.leave.type'].search(
            [('name', 'ilike', 'Annual')],
            limit=1
        )

        # Overtime multipliers (keep your original mapping)
        OT_MULTIPLIERS = {
            'OTW': 1.25,
            'OTR': 1.5,
            'PHO': 1.5,
        }

        for slip in self:
            # Basic validation
            if not slip.employee_id or not slip.date_from or not slip.date_to:
                raise UserError(_("Please set Employee, Date From, and Date To before reconciling lateness."))

            if slip.state != 'draft':
                raise UserError(_("Lateness can only be reconciled while the payslip is in Draft state."))

            if slip.lateness_reconciled:
                # Already done: do nothing (safe idempotency)
                continue

            employee = slip.employee_id

            # ---- 1
