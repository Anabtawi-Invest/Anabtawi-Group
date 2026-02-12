
from odoo import models, fields

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    dashboard_lateness_hours = fields.Float(store=True, readonly=True)
    dashboard_ot_hours = fields.Float(store=True, readonly=True)
    dashboard_ot_bank = fields.Float(store=True, readonly=True)
    dashboard_remaining = fields.Float(store=True, readonly=True)

    # LEGACY SAFE FIELDS
    lateness_hours = fields.Float(store=True, readonly=True)
    ot_hours_total = fields.Float(store=True, readonly=True)
    ot_bank_hours = fields.Float(store=True, readonly=True)
    lateness_remaining = fields.Float(store=True, readonly=True)

    def _recompute_dashboard_fields(self):
        for slip in self:
            lateness = 0.0
            overtime = 0.0

            for line in slip.worked_days_line_ids:
                if line.code == "LAT":
                    lateness += line.number_of_hours or 0.0
                elif line.code in ("OTW","OTR","PHO"):
                    overtime += line.number_of_hours or 0.0

            ot_bank = slip.employee_id.ot_hours_bank or 0.0
            remaining = lateness - ot_bank
            if remaining < 0:
                remaining = 0.0

            slip.dashboard_lateness_hours = lateness
            slip.dashboard_ot_hours = overtime
            slip.dashboard_ot_bank = ot_bank
            slip.dashboard_remaining = remaining

            slip.lateness_hours = lateness
            slip.ot_hours_total = overtime
            slip.ot_bank_hours = ot_bank
            slip.lateness_remaining = remaining
