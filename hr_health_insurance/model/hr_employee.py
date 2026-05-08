# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class Employee(models.Model):
    _inherit = "hr.employee"

    health_insurance_ids = fields.One2many("health.insurance", "employee_id", string="Health Insurances")
    health_document_line_ids = fields.One2many(
        "hr.health.employee.document",
        "employee_id",
        string="HR Documents",
        groups="hr.group_hr_user",
    )
    health_insurance_eligible = fields.Boolean(
        string="Health Insurance UI Eligible",
        compute="_compute_health_insurance_eligible",
        help="When True, the Health Insurance block is shown on the employee form (from 3 months after contract start).",
    )

    @api.depends("contract_date_start")
    def _compute_health_insurance_eligible(self):
        today = fields.Date.today()
        for emp in self:
            start = emp.contract_date_start
            if not start:
                emp.health_insurance_eligible = False
                continue
            threshold = start + relativedelta(months=3)
            emp.health_insurance_eligible = today >= threshold

    @api.onchange('birthday')
    def _onchange_birthday(self):
        employee_hi = self.health_insurance_ids.filtered(lambda x: x.relationship == "employee")
        if employee_hi:
            employee_hi.write({"birthdate": self.birthday})
