from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_construction_vendor = fields.Boolean(
        string="Is Construction Vendor",
        default=False,
        help="Flag indicating this vendor/partner is managed under Construction Budget Control.",
    )
