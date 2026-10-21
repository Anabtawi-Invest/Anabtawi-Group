# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    portal_allow_payment_term = fields.Boolean(
        string="Allow Portal Payment Terms",
        help="If enabled, Sales Portal users can choose payment terms when creating a sale order for this customer.",
        default=False,
    )
