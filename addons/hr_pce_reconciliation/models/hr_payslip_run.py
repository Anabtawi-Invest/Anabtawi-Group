from odoo import models, fields

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    pce_to_reconcile_count = fields.Integer(string="To Reconcile", compute="_compute_pce_counts", store=False)
    pce_need_salary_deduction_count = fields.Integer(string="Needs Salary Deduction", compute="_compute_pce_counts", store=False)

    def _compute_pce_counts(self):
        for run in self:
            slips = run.slip_ids
            run.pce_to_reconcile_count = len(slips.filtered(lambda s: s.reconciliation_state != "done"))
            run.pce_need_salary_deduction_count = len(slips.filtered(lambda s: (s.remaining_after_reconciliation_hours or 0.0) > 0.0))

    def action_pce_mass_reconcile(self):
        for run in self:
            run.slip_ids.action_reconcile_lateness()
        return True

    def action_open_pce_smart_review(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "PCE Smart Review",
            "res_model": "pce.payrun.review.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_run_id": self.id},
        }
