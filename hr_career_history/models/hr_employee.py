from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    career_history_ids = fields.One2many(
        "hr.employee.career.history",
        "employee_id",
        string="Career & Salary History",
        copy=False,
    )
