
from odoo import models, fields, api

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    dashboard_ot_bank = fields.Float(string="OT Bank", store=True, readonly=True)
    dashboard_remaining = fields.Float(string="Remaining", store=True, readonly=True)

    def _recompute_lateness_dashboard(self):
        for slip in self:
            lateness = 0.0
            overtime = 0.0

            for line in slip.worked_days_line_ids:
                if line.code == "LAT":
                    lateness += line.number_of_hours
                if line.code in ("OTW", "OTR", "PHO"):
                    overtime += line.number_of_hours

            ot_bank = slip.employee_id.ot_hours_bank or 0.0

            remaining = lateness - ot_bank
            if remaining < 0:
                remaining = 0.0

            slip.lateness_hours = lateness
            slip.dashboard_ot_bank = ot_bank
            slip.dashboard_remaining = remaining
