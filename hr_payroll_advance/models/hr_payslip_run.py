# -*- coding: utf-8 -*-
from odoo import fields, models

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    pce_total_lateness_hours = fields.Float(string="Total Lateness (Hours)", compute="_compute_pce_totals", store=False)
    pce_total_ot_hours = fields.Float(string="Total OT (Hours)", compute="_compute_pce_totals", store=False)
    pce_total_unpaid_hours = fields.Float(string="Total Unpaid (Hours)", compute="_compute_pce_totals", store=False)

    def _compute_pce_totals(self):
        for run in self:
            slips = run.slip_ids
            run.pce_total_lateness_hours = sum(slips.mapped("pce_lateness_hours"))
            run.pce_total_ot_hours = sum(slips.mapped("pce_ot_hours"))
            run.pce_total_unpaid_hours = sum(slips.mapped("pce_unpaid_hours"))
