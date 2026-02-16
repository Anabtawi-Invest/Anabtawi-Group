from odoo import models

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def action_reconcile_lateness(self):
        for slip in self:
            slip._pce_apply_reconciliation()

    def _pce_apply_reconciliation(self):

        lateness = self.lateness_hours or 0.0
        ot_total = self.ot_total_hours or 0.0
        annual = self.annual_leave_hours or 0.0

        remaining = lateness

        # OT First
        ot_used = min(remaining, ot_total)
        remaining -= ot_used

        # Annual Leave
        leave_used = min(remaining, annual)
        remaining -= leave_used

        # Salary Deduction Input
        if remaining > 0:
            input_type = self.env["hr.payslip.input.type"].search(
                [("code", "=", "LAT_SAL_DED")], limit=1
            )
            if input_type:
                self.env["hr.payslip.input"].create({
                    "payslip_id": self.id,
                    "input_type_id": input_type.id,
                    "amount": remaining,
                })
