from odoo import _, fields, models
from odoo.exceptions import UserError


class DirectSalesGoodsReleaseWizard(models.TransientModel):
    _name = "direct.sales.goods.release.wizard"
    _description = "Direct Sales Goods Release"

    direct_invoice_id = fields.Many2one(
        "direct.sales.invoice",
        required=True,
        readonly=True,
    )
    customer_receiver_name = fields.Char(
        string="Customer Receiver Name",
        required=True,
    )
    payment_clearance_required = fields.Boolean(
        related="direct_invoice_id.payment_clearance_required",
        readonly=True,
    )
    payment_state = fields.Selection(
        related="direct_invoice_id.payment_state",
        readonly=True,
    )

    def action_release(self):
        self.ensure_one()
        if not self.customer_receiver_name or not self.customer_receiver_name.strip():
            raise UserError(_("Enter the name of the person receiving the goods."))
        return self.direct_invoice_id._confirm_goods_release(
            self.customer_receiver_name.strip()
        )
