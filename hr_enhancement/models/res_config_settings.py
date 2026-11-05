# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    daily_leave_type_id = fields.Many2one(
        "hr.leave.type",
        related="company_id.daily_leave_type_id",
        readonly=False,
    )
    daily_conversion_annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        related="company_id.daily_conversion_annual_leave_type_id",
        readonly=False,
    )
