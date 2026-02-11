
from odoo import models, _
from odoo.exceptions import UserError

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_bulk_reconcile_lateness(self):

        slips = self.env["hr.payslip"].browse(
            self.env.context.get("active_ids", [])
        )

        if not slips:
            raise UserError(_("No payslips selected."))

        for slip in slips:
            if hasattr(slip, "_lateness_reconcile_for_slip"):
                slip._lateness_reconcile_for_slip()

        slips._recompute_lateness_dashboard()

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
