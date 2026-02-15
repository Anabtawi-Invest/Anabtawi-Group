# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # =====================================================
    # RECONCILIATION STATUS (BADGE)
    # =====================================================

    reconciliation_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("reconciled", "Reconciled"),
        ],
        default="pending",
        tracking=True,
    )

    # =====================================================
    # DASHBOARD METRICS (SAFE COMPUTE)
    # =====================================================

    late_hours = fields.Float(string="Late Hours", compute="_compute_recon_metrics", store=True)
    ot_total_amount = fields.Float(string="OT Total Amount", compute="_compute_recon_metrics", store=True)
    leave_hours_available = fields.Float(string="Leave Hours", compute="_compute_recon_metrics", store=True)

    ot_deduct_hours = fields.Float(string="OT Deducted")
    leave_deduct_hours = fields.Float(string="Leave Deducted")
    salary_deduct_hours = fields.Float(string="Salary Deducted")

    # =====================================================
    # SAFE COMPUTE ENGINE (NO CONTRACT DEPENDS)
    # =====================================================

    @api.depends("worked_days_line_ids")
    def _compute_recon_metrics(self):
        """
        Enterprise SAFE:
        - Reads Work Entries only
        - No contract_id dependency (fixes registry crash)
        """
        for slip in self:

            late = 0.0
            ot = 0.0

            for line in slip.worked_days_line_ids:

                code = (line.code or "").upper()

                if code == "LAT":
                    late += line.number_of_hours

                if code in ("OTW", "OTR", "PHO"):
                    ot += line.number_of_hours

            slip.late_hours = late
            slip.ot_total_amount = ot

            # LIVE OT BANK FROM EMPLOYEE
            slip.leave_hours_available = getattr(
                slip.employee_id, "x_ot_bank_balance", 0.0
            )

    # =====================================================
    # ENTERPRISE FINAL v3 RECONCILIATION ENGINE
    # =====================================================

    def action_reconcile_lateness_engine(self):
        """
        FULL AUTO v3 ENGINE
        Invisible logic:
        1) Deduct from OT Bank
        2) Deduct from Annual Leave
        3) Remaining becomes Salary deduction
        """

        for slip in self:

            late = slip.late_hours or 0.0
            if not late:
                slip.reconciliation_state = "reconciled"
                continue

            employee = slip.employee_id

            # -------------------------------------------------
            # STEP 1 — OT BANK
            # -------------------------------------------------

            ot_bank = getattr(employee, "x_ot_bank_balance", 0.0)

            ot_deduct = min(late, ot_bank)

            late -= ot_deduct
            slip.ot_deduct_hours = ot_deduct

            if hasattr(employee, "x_ot_bank_balance"):
                employee.x_ot_bank_balance -= ot_deduct

            # -------------------------------------------------
            # STEP 2 — ANNUAL LEAVE (SAFE)
            # -------------------------------------------------

            leave_balance = 0.0

            if hasattr(employee, "remaining_leaves"):
                leave_balance = employee.remaining_leaves

            leave_deduct = min(late, leave_balance)

            late -= leave_deduct
            slip.leave_deduct_hours = leave_deduct

            # NOTE:
            # We DO NOT write to Time Off here.
            # LAT_REC salary rule handles accounting side.

            # -------------------------------------------------
            # STEP 3 — SALARY DEDUCTION
            # -------------------------------------------------

            salary_deduct = late if late > 0 else 0.0
            slip.salary_deduct_hours = salary_deduct

            # -------------------------------------------------
            # FINAL STATUS
            # -------------------------------------------------

            slip.reconciliation_state = "reconciled"

        return True
