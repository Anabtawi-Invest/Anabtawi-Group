from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    delivery_group_id = fields.Many2one(
        "sale.delivery.group",
        string="Delivery Group",
        index="btree_not_null",
    )

    def write(self, vals):
        if "delivery_group_id" in vals:
            locked_lines = self.filtered(
                lambda l: l.delivery_group_id.id != vals["delivery_group_id"]
                and l.move_ids.filtered(lambda m: m.state != "cancel")
            )
            if locked_lines:
                raise UserError(_(
                    "You cannot change the delivery group of lines that already have deliveries:\n%s",
                    "\n".join(locked_lines.mapped("display_name")),
                ))
        return super().write(vals)

    def _check_delivery_group(self):
        missing = self.filtered(
            lambda l: l.order_id.use_delivery_group
            and not l.display_type
            and l.product_id.type == "consu"
            and not l.delivery_group_id
        )
        if missing:
            raise UserError(_(
                "Please set a Delivery Group on the following lines:\n%s",
                "\n".join(missing.mapped("display_name")),
            ))

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        if not self.env.context.get("skip_procurement"):
            self.filtered(lambda l: l.state == "sale" and not l.order_id.locked)._check_delivery_group()
        return super()._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        if self.order_id.use_delivery_group:
            values["delivery_group_id"] = self.delivery_group_id
        return values
