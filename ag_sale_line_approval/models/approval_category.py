from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    sale_line_approval_enabled = fields.Boolean(
        string="Sale Line Approval",
        help="Use this approval category for sale order line discount or price override requests.",
    )
    sale_line_approval_type = fields.Selection(
        selection=[
            ("discount", "Discount"),
            ("price_override", "Price Override"),
        ],
        string="Sale Approval Type",
    )
    sale_discount_min = fields.Float(string="Discount From (%)")
    sale_discount_max = fields.Float(string="Discount To (%)")

    @api.constrains(
        "sale_line_approval_enabled",
        "sale_line_approval_type",
        "sale_discount_min",
        "sale_discount_max",
    )
    def _check_sale_discount_range(self):
        for category in self.filtered(
            lambda cat: cat.sale_line_approval_enabled and cat.sale_line_approval_type == "discount"
        ):
            if category.sale_discount_max <= 0.0:
                raise ValidationError(_("The discount upper bound must be greater than zero."))
            if category.sale_discount_max < category.sale_discount_min:
                raise ValidationError(_("The discount upper bound must be greater than or equal to the lower bound."))
