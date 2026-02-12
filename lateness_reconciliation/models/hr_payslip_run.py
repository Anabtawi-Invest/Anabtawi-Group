from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    dashboard_total_lateness = fields.Float(compute="_compute_dashboard_totals")
    dashboard_total_overtime = fields.Float(compute="_compute_dashboard_totals")
    dashboard_total_remaining = fields.Float(compute="_compute_dashboard_totals")
    dashboard_coverage_pct = fields.Float(compute="_compute_dashboard_totals")

    @api.depends(
        "slip_ids.dashboard_lateness_hours",
        "slip_ids.dashboard_ot_hours",
        "slip_ids.dashboard_remaining",
    )
    def _compute_dashboard_totals(self):
        for run in self:
            slips = run.slip_ids
            total_lateness = sum(slips.mapped("dashboard_lateness_hours"))
            total_overtime = sum(slips.mapped("dashboard_ot_hours"))
            total_remaining = sum(slips.mapped("dashboard_remaining"))

            run.dashboard_total_lateness = total_lateness
            run.dashboard_total_overtime = total_overtime
            run.dashboard_total_remaining = total_remaining

            if total_lateness > 0:
                run.dashboard_coverage_pct = (
                    (total_lateness - total_remaining) / total_lateness
                ) * 100
            else:
                run.dashboard_coverage_pct = 100.0

    def action_mass_reconcile_lateness_enterprise(self):

        slips = self.env["hr.payslip"].browse(
            self.env.context.get("active_ids", [])
        )

        if not slips:
            raise UserError(_("No payslips selected."))

        slips = slips.filtered(lambda s: s.state == "draft")

        for slip in slips:
            if hasattr(slip, "_lateness_reconcile_for_slip"):
                slip._lateness_reconcile_for_slip()

        slips._recompute_dashboard_fields()

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
