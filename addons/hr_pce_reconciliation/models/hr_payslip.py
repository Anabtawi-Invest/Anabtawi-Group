from odoo import models, fields


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    lateness_hours = fields.Float()
    ot_total_hours = fields.Float()
    annual_leave_hours = fields.Float()

    def _pce_apply_reconciliation(self):

        for slip in self:

            lateness = slip.lateness_hours or 0.0
            ot_total = slip.ot_total_hours or 0.0
            annual = slip.annual_leave_hours or 0.0

            remaining = lateness - ot_total - annual

            # ENGINELESS → only create salary input if needed
            if remaining > 0:

                existing = slip.input_line_ids.filtered(
                    lambda x: x.code == "LAT_SAL_DED"
                )

                if existing:
                    existing.amount = remaining
                else:
                    self.env["hr.payslip.input"].create({
                        "payslip_id": slip.id,
                        "name": "Lateness Salary Deduction",
                        "code": "LAT_SAL_DED",
                        "amount": remaining,
                    })
