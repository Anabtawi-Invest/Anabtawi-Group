# -*- coding: utf-8 -*-
from odoo import models, fields


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Stored dashboard fields so list view updates reliably after server actions (Odoo 19 Owl).
    dashboard_lateness_hours = fields.Float(string="Lateness (h)", digits=(16, 2), readonly=True, store=True)
    dashboard_ot_hours = fields.Float(string="Overtime (h)", digits=(16, 2), readonly=True, store=True)
    dashboard_ot_bank = fields.Float(string="OT Bank (h)", digits=(16, 2), readonly=True, store=True)
    dashboard_remaining = fields.Float(string="Remaining (h)", digits=(16, 2), readonly=True, store=True)

    def _dashboard_read_hours(self):
        """Read hours from worked days lines (work entries aggregation).
        Uses your configured codes:
          LAT for lateness
          OTW/OTR/PHO for overtime (weekday/weekend/holiday)
        """
        self.ensure_one()
        lateness = 0.0
        overtime = 0.0
        for line in self.worked_days_line_ids:
            code = line.code
            if code == "LAT":
                lateness += line.number_of_hours or 0.0
            elif code in ("OTW", "OTR", "PHO"):
                overtime += line.number_of_hours or 0.0
        return lateness, overtime

    def _recompute_dashboard_fields(self):
        """Enterprise-safe: HOURS only (no money). Stored for list visibility."""
        for slip in self:
            lateness, overtime = slip._dashboard_read_hours()
            ot_bank = slip.employee_id.ot_hours_bank or 0.0  # confirmed from your ZIP
            remaining = lateness - ot_bank
            if remaining < 0:
                remaining = 0.0

            slip.dashboard_lateness_hours = lateness
            slip.dashboard_ot_hours = overtime
            slip.dashboard_ot_bank = ot_bank
            slip.dashboard_remaining = remaining
