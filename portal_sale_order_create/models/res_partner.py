# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    portal_allow_payment_term = fields.Boolean(
        string="Allow Portal Payment Terms",
        help="If enabled, Sales Portal users can choose payment terms when creating a sale order for this customer.",
        default=False,
    )
    van_portal_user_id = fields.Many2one(
        "res.users",
        string="Van Portal User",
        copy=False,
        index=True,
        domain="[('share', '=', True)]",
        help="Portal van user who owns this credit customer. "
        "Used for Credit Sale listing (not the standard Salesperson field).",
    )
