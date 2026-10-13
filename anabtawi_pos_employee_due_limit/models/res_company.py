# -*- coding: utf-8 -*-

from odoo import fields, models

DUE_LIMIT_FIELDS = (
    "employee_due_limit_enabled",
    "employee_due_deduction_percent",
    "employee_due_max_percent",
)


class ResCompany(models.Model):
    _inherit = "res.company"

    employee_due_limit_enabled = fields.Boolean(
        string="Employee Due Limit",
        help="Fill employees' credit limit from their wage and block POS Customer Account "
        "orders that exceed it.",
    )
    employee_due_deduction_percent = fields.Float(
        string="Wage Deduction %",
        default=7.5,
        help="Percentage deducted from the wage to get the net wage (e.g. social security).",
    )
    employee_due_max_percent = fields.Float(
        string="Max Due % of Net Wage",
        default=10.0,
        help="Maximum Customer Account due allowed, as a percentage of the net wage.",
    )

    def write(self, vals):
        if vals.get("employee_due_limit_enabled"):
            vals = dict(vals, account_use_credit_limit=True)
        res = super().write(vals)
        if any(field in vals for field in DUE_LIMIT_FIELDS):
            employees = self.env["hr.employee"].sudo().search([("company_id", "in", self.ids)])
            employees._sync_employee_due_credit_limit()
        return res
