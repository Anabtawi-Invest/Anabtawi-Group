from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    overtime_bank_balance = fields.Monetary(
        string="OT Bank Balance (OT_TOTAL)",
        compute="_compute_overtime_bank_balance",
        currency_field="company_currency_id",
    )

    def _compute_overtime_bank_balance(self):
        for emp in self:
            lines = self.env["hr.payslip.line"].search(
                [
                    ("employee_id", "=", emp.id),
                    ("code", "=", "OT_TOTAL"),
                    ("slip_id.state", "=", "done"),
                ]
            )
            emp.overtime_bank_balance = sum(lines.mapped("total"))
