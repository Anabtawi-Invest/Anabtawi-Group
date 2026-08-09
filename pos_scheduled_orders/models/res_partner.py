# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    building_apt = fields.Char(
        string="Building / Apt (البناية / الشقة)",
        help="Building name, Apartment number, or Floor details for delivery.",
    )
