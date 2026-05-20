from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    pos_adv_is_advance_order = fields.Boolean(string="Advance Order", default=False)
    pos_adv_requested_datetime = fields.Datetime(string="Requested Date/Time")
    pos_adv_note = fields.Text(string="Advance Order Note")

    @api.model
    def _order_fields(self, ui_order):
        """Receive extra fields from POS UI when an order is pushed."""
        res = super()._order_fields(ui_order)
        res.update({
            "pos_adv_is_advance_order": bool(ui_order.get("pos_adv_is_advance_order", False)),
            "pos_adv_requested_datetime": ui_order.get("pos_adv_requested_datetime") or False,
            "pos_adv_note": ui_order.get("pos_adv_note") or False,
        })
        return res
