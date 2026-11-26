from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    receipt_same_month_enabled = fields.Boolean(
        related="company_id.purchase_receipt_same_month",
    )
    allow_receipt_other_month = fields.Boolean(
        string="Allow receipt in another month",
        copy=False,
        tracking=True,
        help="Receipts for this purchase order can be validated in a month other "
        "than the purchase order confirmation month.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_allow_receipt_other_month_access(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_allow_receipt_other_month_access(vals)
        return super().write(vals)

    def _check_allow_receipt_other_month_access(self, vals):
        if "allow_receipt_other_month" not in vals or self.env.su:
            return
        if self.env.user.has_group(
            "purchase_receipt_same_month.group_purchase_receipt_other_month"
        ):
            return
        raise UserError(_(
            "You are not allowed to change receipt validation for another month "
            "on a purchase order."
        ))
