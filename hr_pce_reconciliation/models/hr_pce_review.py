# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPceReviewLine(models.Model):
    _name = "hr.pce.review.line"
    _description = "PCE Smart Review Line"
    _order = "badge_state desc, employee_id"

    run_id = fields.Many2one("hr.payslip.run", required=True, ondelete="cascade", index=True)
    payslip_id = fields.Many2one("hr.payslip", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)

    ot_total_hours = fields.Float(string="OT Total")
    lateness_hours = fields.Float(string="Lateness")
    annual_available_hours = fields.Float(string="Annual Leave")
    remaining_hours = fields.Float(string="Remaining")

    badge_state = fields.Selection(
        [("ok", "OK"), ("warning", "Needs Review"), ("danger", "Deduction")],
        compute="_compute_badge_state",
        store=True,
    )

    @api.depends("remaining_hours", "lateness_hours")
    def _compute_badge_state(self):
        for rec in self:
            if (rec.remaining_hours or 0.0) > 0:
                rec.badge_state = "danger"
            elif (rec.lateness_hours or 0.0) > 0:
                rec.badge_state = "warning"
            else:
                rec.badge_state = "ok"
