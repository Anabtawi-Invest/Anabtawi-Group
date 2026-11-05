# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    daily_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Daily Time Off Type",
        help="Hours taken from this leave type are accumulated per employee. "
             "Every 8 hours create 1 day of the annual leave type below.",
    )
    daily_conversion_annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Annual Leave Type for Daily Conversion",
        help="Leave type used when 8 hours of the daily time off type are converted into 1 annual leave day.",
    )
