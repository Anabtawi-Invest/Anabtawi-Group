# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _


class HrPayrollUnifiedReport(models.Model):
    _name = "hr.payroll.unified.report"
    _description = "Unified HR & Payroll Operations Analysis"
    _auto = False
    _order = "date_to desc, id desc"

    payslip_id = fields.Many2one("hr.payslip", string="Payslip", readonly=True)
    payslip_run_id = fields.Many2one("hr.payslip.run", string="Payrun Batch", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", readonly=True)
    employee_code = fields.Char(string="Emp No.", readonly=True)
    department_id = fields.Many2one("hr.department", string="Department", readonly=True)
    job_id = fields.Many2one("hr.job", string="Job Position", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    date_from = fields.Date(string="Date From", readonly=True)
    date_to = fields.Date(string="Date To", readonly=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("verify", "Waiting"),
        ("done", "Done"),
        ("paid", "Paid"),
        ("cancel", "Cancelled"),
    ], string="Status", readonly=True)
    
    basic_salary = fields.Float(string="Basic Wage", readonly=True)
    allowance_amount = fields.Float(string="Allowances", readonly=True)
    overtime_amount = fields.Float(string="Overtime Amount", readonly=True)
    overtime_hours = fields.Float(string="Overtime Hours", readonly=True)
    lateness_hours = fields.Float(string="Lateness Hours", readonly=True)
    gross_salary = fields.Float(string="Gross Salary", readonly=True)
    deduction_amount = fields.Float(string="Deductions", readonly=True)
    social_security_amount = fields.Float(string="Social Security (Emp)", readonly=True)
    tax_amount = fields.Float(string="Income Tax", readonly=True)
    net_salary = fields.Float(string="Net Salary", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW hr_payroll_unified_report AS (
                SELECT
                    p.id AS id,
                    p.id AS payslip_id,
                    p.payslip_run_id AS payslip_run_id,
                    p.employee_id AS employee_id,
                    COALESCE(e.registration_number, e.barcode, CAST(e.id AS VARCHAR)) AS employee_code,
                    p.department_id AS department_id,
                    e.job_id AS job_id,
                    p.company_id AS company_id,
                    p.date_from AS date_from,
                    p.date_to AS date_to,
                    p.state AS state,
                    COALESCE(p.basic_wage, 0.0) AS basic_salary,
                    COALESCE((
                        SELECT SUM(pl.total)
                        FROM hr_payslip_line pl
                        LEFT JOIN hr_salary_rule_category rc ON pl.category_id = rc.id
                        WHERE pl.slip_id = p.id AND (rc.code IN ('ALW', 'ALLOWANCE') OR pl.code ILIKE '%ALW%' OR pl.code ILIKE '%BONUS%')
                    ), 0.0) AS allowance_amount,
                    COALESCE((
                        SELECT SUM(pl.total)
                        FROM hr_payslip_line pl
                        WHERE pl.slip_id = p.id AND (pl.code ILIKE '%OT%' OR pl.code ILIKE '%OVERTIME%')
                    ), 0.0) AS overtime_amount,
                    COALESCE((
                        SELECT SUM(wd.number_of_hours)
                        FROM hr_payslip_worked_days wd
                        WHERE wd.payslip_id = p.id AND (wd.code ILIKE '%OT%' OR wd.code ILIKE '%EXTRA%')
                    ), 0.0) AS overtime_hours,
                    COALESCE((
                        SELECT SUM(wd.number_of_hours)
                        FROM hr_payslip_worked_days wd
                        WHERE wd.payslip_id = p.id AND (wd.code ILIKE '%LATE%' OR wd.code ILIKE '%UNPAID%')
                    ), 0.0) AS lateness_hours,
                    COALESCE(p.gross_wage, 0.0) AS gross_salary,
                    COALESCE((
                        SELECT SUM(ABS(pl.total))
                        FROM hr_payslip_line pl
                        LEFT JOIN hr_salary_rule_category rc ON pl.category_id = rc.id
                        WHERE pl.slip_id = p.id AND (rc.code IN ('DED', 'DEDUCTION') OR pl.code ILIKE '%DED%' OR pl.code ILIKE '%LOAN%')
                    ), 0.0) AS deduction_amount,
                    COALESCE((
                        SELECT SUM(ABS(pl.total))
                        FROM hr_payslip_line pl
                        WHERE pl.slip_id = p.id AND (pl.code ILIKE '%SS%' OR pl.code ILIKE '%SSC%' OR pl.name ILIKE '%ضمان%')
                    ), 0.0) AS social_security_amount,
                    COALESCE((
                        SELECT SUM(ABS(pl.total))
                        FROM hr_payslip_line pl
                        WHERE pl.slip_id = p.id AND (pl.code ILIKE '%TAX%' OR pl.name ILIKE '%ضريبة%')
                    ), 0.0) AS tax_amount,
                    COALESCE(p.net_wage, 0.0) AS net_salary
                FROM hr_payslip p
                LEFT JOIN hr_employee e ON p.employee_id = e.id
                WHERE p.state != 'cancel'
            )
        """)

    def action_open_payslip(self):
        self.ensure_one()
        return {
            "name": _("Payslip Details"),
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
            "view_mode": "form",
            "res_id": self.payslip_id.id,
            "target": "current",
        }
