# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    overtime_bank_hours = fields.Float(
        string="OT Bank (Hours)",
        help="Running overtime bank balance in hours. Increased by approved OT, decreased when lateness is reconciled against OT bank.",
        default=0.0,
        tracking=True,
    )
