from odoo import models, fields

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    pce_to_reconcile_count = fields.Integer(string="To Reconcile", compute="_compute_pce_counts", store=False)
    pce_has_deduction_count = fields.Integer(string="Needs Salary Deduction", compute="_compute_pce_counts", store=False)

    def _compute_pce_counts(self):
        for run in self:
            slips = run.slip_ids
            run.pce_to_reconcile_count = len(slips.filtered(lambda s: s.reconciliation_state != "done"))
            run.pce_has_deduction_count = len(slips.filtered(lambda s: (s.remaining_after_reconciliation_hours or 0.0) > 0.0))

    def action_pce_mass_reconcile(self):
        for run in self:
            run.slip_ids.action_reconcile_lateness()
        return True

    def action_open_pce_to_reconcile(self):
        self.ensure_one()
        action = self.env.ref("hr_payroll.action_view_hr_payslip_form").read()[0]
        action["domain"] = [("payslip_run_id", "=", self.id), ("reconciliation_state", "!=", "done")]
        return action

    def action_open_pce_need_deduction(self):
        self.ensure_one()
        action = self.env.ref("hr_payroll.action_view_hr_payslip_form").read()[0]
        action["domain"] = [("payslip_run_id", "=", self.id), ("remaining_after_reconciliation_hours", ">", 0)]
        return action
