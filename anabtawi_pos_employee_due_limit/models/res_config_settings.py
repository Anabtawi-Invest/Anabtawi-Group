# -*- coding: utf-8 -*-

from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    employee_due_limit_enabled = fields.Boolean(
        related="company_id.employee_due_limit_enabled", readonly=False
    )
    employee_due_deduction_percent = fields.Float(
        related="company_id.employee_due_deduction_percent", readonly=False
    )
    employee_due_max_percent = fields.Float(
        related="company_id.employee_due_max_percent", readonly=False
    )

    def action_recompute_employee_due_limits(self):
        self.ensure_one()
        employees = self.env["hr.employee"].sudo().search([("company_id", "=", self.company_id.id)])
        employees._sync_employee_due_credit_limit()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Employee Due Limits"),
                "message": _("Credit limits recomputed for %s employee(s).", len(employees)),
                "type": "success",
            },
        }
