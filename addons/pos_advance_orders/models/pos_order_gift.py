from odoo import models

class PosOrder(models.Model):
    _inherit = "pos.order"

    def _order_line_fields(self, line, session_id=None):
        res = super()._order_line_fields(line, session_id=session_id)

        # line is the JSON dict coming from POS UI
        if line.get("is_gift"):
            res["is_gift"] = True
            res["gift_original_price_unit"] = line.get("gift_original_price_unit", 0.0) or 0.0
        else:
            res["is_gift"] = False
            res["gift_original_price_unit"] = 0.0

        return res
