from odoo import models, _


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _raise_if_sale_approval_block(self, operation_label):
        sale_orders = self.mapped("sale_id")
        if sale_orders:
            sale_orders._raise_if_sale_line_approvals_block(operation_label)

    def action_assign(self):
        self._raise_if_sale_approval_block(_("reserve products for delivery"))
        return super().action_assign()

    def button_validate(self):
        self._raise_if_sale_approval_block(_("validate this delivery"))
        return super().button_validate()
