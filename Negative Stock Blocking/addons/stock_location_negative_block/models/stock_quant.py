# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def action_apply_inventory(self):
        for quant in self:
            location = quant.location_id

            # 1️⃣ إذا لا يوجد تقييد على الموقع → تجاهل
            if not location or not location.restrict_negative:
                continue

            # 2️⃣ الفرق في الجرد (الذي سيُطبق)
            diff_qty = quant.inventory_diff_quantity
            if not diff_qty:
                continue

            # 3️⃣ إذا الجرد سيُنقص المخزون
            if diff_qty < 0:
                qty_after = quant.available_quantity + diff_qty

                if qty_after < 0:
                    raise UserError(_(
                        "You cannot apply this Inventory Adjustment.\n\n"
                        "Product: %s\n"
                        "Location: %s\n"
                        "Available Quantity: %s\n"
                        "Inventory Difference: %s"
                    ) % (
                        quant.product_id.display_name,
                        location.display_name,
                        quant.available_quantity,
                        diff_qty,
                    ))

        # إذا لا يوجد منع → نكمل التطبيق
        return super().action_apply_inventory()
