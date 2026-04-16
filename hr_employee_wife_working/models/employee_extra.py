from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    spouse_employed = fields.Boolean(string="Spouse Employed")
