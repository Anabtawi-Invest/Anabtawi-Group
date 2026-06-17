from odoo import _, fields, models
from odoo.tools import float_is_zero


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _process_payment_lines(self, pos_order, order, pos_session, draft):
        """Force a payment line on zero-total paid orders."""
        super()._process_payment_lines(pos_order, order, pos_session, draft)

        if draft or order.payment_ids:
            return

        if not float_is_zero(order.amount_total, precision_rounding=order.currency_id.rounding):
            return

        payment_method = pos_session.payment_method_ids.filtered(lambda pm: pm.type != "pay_later")[:1]
        if not payment_method:
            payment_method = pos_session.payment_method_ids[:1]
        if not payment_method:
            return

        order.add_payment({
            "name": _("Free order payment"),
            "pos_order_id": order.id,
            "amount": 0.0,
            "payment_date": fields.Datetime.now(),
            "payment_method_id": payment_method.id,
        })
