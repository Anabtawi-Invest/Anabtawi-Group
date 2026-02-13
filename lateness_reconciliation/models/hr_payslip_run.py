from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    total_lateness = fields.Float(compute="_compute_totals")
    total_overtime = fields.Float(compute="_compute_totals")
    total_remaining = fields.Float(compute="_compute_totals")
    coverage_pct = fields.Float(compute="_compute_totals")

    @api.depends(
        "slip_ids.lateness_hours",
        "slip_ids.overtime_hours",
        "slip_ids.remaining_lateness_hours",
    )
    def _compute_totals(self):
        for run in self:
            slips = run.slip_ids
            total_lateness = sum(slips.mapped("lateness_hours"))
            total_overtime = sum(slips.mapped("overtime_hours"))
            total_remaining = sum(slips.mapped("remaining_lateness_hours"))

            run.total_lateness = total_lateness
            run.total_overtime = total_overtime
            run.total_remaining = total_remaining

            if total_lateness > 0:
                run.coverage_pct = ((total_lateness - total_remaining) / total_lateness) * 100
            else:
                run.coverage_pct = 100.0

    def action_mass_reconcile_lateness(self):
        # Called from server action on Pay Run form
        slips = self.env["hr.payslip"].browse(self.env.context.get("active_ids", []))
        if not slips:
            raise UserError(_("No payslips selected."))

        slips = slips.filtered(lambda s: s.state == "draft")
        for slip in slips:
            if hasattr(slip, "_lateness_reconcile_for_slip_no_ot_bank"):
                slip._lateness_reconcile_for_slip_no_ot_bank()

        return {"type": "ir.actions.client", "tag": "reload"}
