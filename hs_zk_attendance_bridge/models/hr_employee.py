# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    device_id_num = fields.Char(
        string="Biometric Device ID",
        help="Identifier used by the biometric device or bridge agent for this employee.",
    )
