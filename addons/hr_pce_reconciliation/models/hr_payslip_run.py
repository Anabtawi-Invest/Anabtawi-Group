from odoo import models, fields, api


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    # ===============================
    # ENGINELESS SMART COUNTERS
    # ===============================

    pce_to_reconcile_count = fields.Integer(
        string="To Reconcile",
        compute="_compute_pce_counts",
    )

    pce_need_salary_deduction_count = fields.Integer(
        string="Needs Salary Deduction",
        compute="_compute_pce_counts",
    )

    # ===============================
    # COMPUTE COUNTS
    # ===============================

    def _compute_pce_counts(self):
        for run in self:

            to_reconcile = 0
            need_salary = 0

            for slip in run.slip_ids:

                lateness = getattr(slip, "lateness_hours", 0.0)
                ot_total = getattr(slip, "ot_total_hours", 0.0)
                annual = getattr(slip, "annual_leave_hours", 0.0)

                remaining = lateness - ot_total - annual

                if lateness > 0:
                    to_reconcile += 1

                if remaining > 0:
                    need_salary += 1

            run.pce_to_reconcile_count = to_reconcile
            run.pce_need_salary_deduction_count = need_salary

    # ===============================
    # MASS RECONCILIATION
    # ===============================

    def action_pce_mass_reconcile(self):

        for run in self:
            for slip in run.slip_ids:

                if hasattr(slip, "_pce_apply_reconciliation"):
                    slip._pce_apply_reconciliation()

        return True

    # ===============================
    # OPEN SMART REVIEW (ENGINELESS)
    # ===============================

    def action_open_pce_smart_review(self):

        self.ensure_one()

        smart_review_model = self.env["pce.smart.review"]

        # Clean old review lines
        smart_review_model.search([]).unlink()

        for slip in self.slip_ids:

            lateness = getattr(slip, "lateness_hours", 0.0)
            ot_total = getattr(slip, "ot_total_hours", 0.0)
            annual = getattr(slip, "annual_leave_hours", 0.0)

            remaining = lateness - ot_total - annual

            smart_review_model.create({
                "employee_id": slip.employee_id.id,
                "payslip_id": slip.id,
                "lateness_hours": lateness,
                "ot_total_hours": ot_total,
                "annual_leave_hours": annual,
                "remaining_hours": remaining,
            })

        return {
            "type": "ir.actions.act_window",
            "name": "Smart Review",
            "res_model": "pce.smart.review",
            "view_mode": "tree",
            "target": "current",
        }
