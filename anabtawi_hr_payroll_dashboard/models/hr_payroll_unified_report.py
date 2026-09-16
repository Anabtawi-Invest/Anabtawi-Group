# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class HrPayrollUnifiedReport(models.TransientModel):
    _name = "hr.payroll.unified.report"
    _description = "Unified HR & Payroll Operations Analysis Report"
    _order = "date_to desc, id desc"

    name = fields.Char(string="Description / Slip Ref")
    payslip_id = fields.Many2one("hr.payslip", string="Payslip", index=True)
    payslip_run_id = fields.Many2one("hr.payslip.run", string="Payrun Batch", index=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", index=True)
    department_id = fields.Many2one("hr.department", string="Department", index=True)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company)
    date_from = fields.Date(string="Date From")
    date_to = fields.Date(string="Date To")
    state = fields.Selection([
        ("draft", "Draft"),
        ("verify", "Waiting"),
        ("done", "Done"),
        ("paid", "Paid"),
        ("cancel", "Cancelled"),
    ], string="Status", default="done")
    
    basic_salary = fields.Float(string="Basic Wage", digits=(16, 3))
    allowance_amount = fields.Float(string="Allowances", digits=(16, 3))
    overtime_amount = fields.Float(string="Overtime Amount", digits=(16, 3))
    overtime_hours = fields.Float(string="Overtime Hours", digits=(16, 2))
    lateness_hours = fields.Float(string="Lateness Hours", digits=(16, 2))
    gross_salary = fields.Float(string="Gross Salary", digits=(16, 3))
    deduction_amount = fields.Float(string="Deductions", digits=(16, 3))
    social_security_amount = fields.Float(string="Social Security (Emp)", digits=(16, 3))
    tax_amount = fields.Float(string="Income Tax", digits=(16, 3))
    net_salary = fields.Float(string="Net Salary", digits=(16, 3))

    def action_open_payslip(self):
        self.ensure_one()
        if self.payslip_id:
            return {
                "name": _("Payslip Details"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip",
                "res_id": self.payslip_id.id,
                "view_mode": "form",
                "target": "current",
            }
        return False

    def action_export_excel(self):
        wiz = self.env["hr.payroll.report.wizard"].sudo().create({
            "report_type": "all",
            "date_from": self.date_from or fields.Date.today().replace(day=1),
            "date_to": self.date_to or fields.Date.today(),
        })
        return wiz.action_export_xlsx()
