# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class EmployeeJoDependantLine(models.Model):
    _name = "employee.jo.dependant.line"
    _description = "Jordan employee dependant child"
    _order = "id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Child's Name", required=True)
    place_of_birth = fields.Char(string="Place of Birth")
    birthdate = fields.Date(string="Date of Birth")
    national_number = fields.Char(string="National Number")

    @api.constrains("national_number")
    def _check_unique_child_national_per_employee(self):
        for line in self:
            num = (line.national_number or "").strip()
            if not num or not line.employee_id:
                continue
            other = line.sudo().search(
                [
                    ("id", "!=", line.id),
                    ("employee_id", "=", line.employee_id.id),
                    ("national_number", "=ilike", num),
                ],
                limit=1,
            )
            if other:
                raise ValidationError(
                    _("The same national number cannot be repeated for another line of this employee.")
                )
