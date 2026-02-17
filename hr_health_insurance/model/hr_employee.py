# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class Employee(models.Model):
    _inherit = "hr.employee"

    health_insurance_ids = fields.One2many("health.insurance", "employee_id", string="Health Insurances")

    @api.onchange('birthday')
    def _onchange_birthday(self):
        employee_hi = self.health_insurance_ids.filtered(lambda x: x.relationship == "employee")
        if employee_hi:
            employee_hi.write({"birthdate": self.birthday})
