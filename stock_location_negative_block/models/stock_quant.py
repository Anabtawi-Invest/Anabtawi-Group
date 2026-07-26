# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _apply_inventory(self, inventory_date=None):

        for quant in self:
            location = quant.location_id

            # فقط إذا الموقع عليه التقييد
            if not location or not location.restrict_negative:
                continue

            # الكمية الحالية في النظام
            current_qty = quant.quantity

            # الكمية التي أدخلها المستخدم (Counted)
            counted_qty = quant.inventory_quantity

            # إذا لم يتم إدخال قيمة → تجاهل
            if counted_qty is False:
                continue

            # الفرق الحقيقي
            diff_qty = counted_qty - current_qty

            # فقط إذا الجرد سيُنقص المخزون
            if diff_qty < 0:
                qty_after = current_qty + diff_qty

                if qty_after < 0:
                    raise UserError(_(
                        "You cannot apply this Inventory Adjustment.\n\n"
                        "Product: %s\n"
                        "Location: %s\n"
                        "Current Quantity: %s\n"
                        "Counted Quantity: %s"
                    ) % (
                        quant.product_id.display_name,
                        location.display_name,
                        current_qty,
                        counted_qty,
                    ))

        return super()._apply_inventory(inventory_date)
