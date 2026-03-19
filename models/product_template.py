from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    branch_allowed = fields.Boolean(
        string="Allowed for Branch Internal Transfers",
        help="If enabled, branch users can select this product in internal transfers.",
        default=False,
    )
