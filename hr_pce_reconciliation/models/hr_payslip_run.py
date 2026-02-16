# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    pce_deduction_count = fields.Integer(string="PCE Deductions", compute="_compute_pce_counts")

    @api.depends("slip_ids.pce_remaining_hours")
    def _compute_pce_counts(self):
        for run in self:
            run.pce_deduction_count = sum(1 for s in run.slip_ids if (s.pce_remaining_hours or 0.0) > 0)

    def action_pce_mass_reconcile(self):
        for run in self:
            if not run.slip_ids:
                raise UserError(_("No payslips in this payrun."))
            run.slip_ids.action_pce_reconcile()
        return True

    def action_open_pce_review(self):
        self.ensure_one()

        Review = self.env["hr.pce.review.line"].sudo()

        # delete previous review lines for THIS run only
        Review.search([("run_id", "=", self.id)]).unlink()

        for slip in self.slip_ids:
            Review.create({
                "run_id": self.id,
                "payslip_id": slip.id,
                "employee_id": slip.employee_id.id,
                "ot_total_hours": slip.pce_ot_total_hours,
                "lateness_hours": slip.pce_lateness_hours,
                "annual_available_hours": slip.pce_annual_available_hours,
                "remaining_hours": slip.pce_remaining_hours,
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Smart Review"),
            "res_model": "hr.pce.review.line",
            "view_mode": "tree",
            "domain": [("run_id", "=", self.id)],
            "target": "current",
        }
