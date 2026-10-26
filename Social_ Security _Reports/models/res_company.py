# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    ssc_establishment_number = fields.Char(
        string="Social Security Establishment No.",
        default="2883",
        help="Jordanian Social Security Facility / Establishment Number (e.g. 2883)"
    )
    ssc_contribution_rate = fields.Float(
        string="Social Security Contribution Rate (%)",
        default=21.75,
        help="Standard Jordanian Social Security deduction percentage (e.g. 21.75%)"
    )
    ssc_licensed_to = fields.Char(
        string="SSC Licensed To Name",
        default="Anabtawi Sweets",
        help="Licensed company name printed on social security reports"
    )
