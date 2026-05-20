from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Advance order metadata
    pos_adv_is_advance_order = fields.Boolean(string="Advance Order", default=False, index=True)
    pos_adv_type = fields.Selection(
        [("pickup", "Pickup"), ("delivery", "Delivery")],
        string="Advance Type",
        default="pickup",
    )
    pos_adv_requested_datetime = fields.Datetime(string="Requested Date/Time")
    pos_adv_contact_name = fields.Char(string="Contact Name")
    pos_adv_phone = fields.Char(string="Phone")
    pos_adv_address = fields.Text(string="Address")
    pos_adv_note = fields.Text(string="Note")
    pos_adv_deposit = fields.Monetary(string="Deposit", currency_field="currency_id")

    @api.model
    def _order_fields(self, ui_order):
        """Receive extra fields from POS UI when an order is pushed."""
        res = super()._order_fields(ui_order)
        res.update({
            "pos_adv_is_advance_order": bool(ui_order.get("pos_adv_is_advance_order", False)),
            "pos_adv_type": ui_order.get("pos_adv_type") or "pickup",
            "pos_adv_requested_datetime": ui_order.get("pos_adv_requested_datetime") or False,
            "pos_adv_contact_name": ui_order.get("pos_adv_contact_name") or False,
            "pos_adv_phone": ui_order.get("pos_adv_phone") or False,
            "pos_adv_address": ui_order.get("pos_adv_address") or False,
            "pos_adv_note": ui_order.get("pos_adv_note") or False,
            "pos_adv_deposit": ui_order.get("pos_adv_deposit") or 0.0,
        })
        return res
