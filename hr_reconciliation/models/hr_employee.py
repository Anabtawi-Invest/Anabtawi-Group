# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    overtime_bank_hours = fields.Float(
        string="OT Bank (Hours)",
        default=0.0,
        tracking=True,
        help="Running OT bank in hours. Updated by v19.2 reconciliation safely (no double counting).",
    )
