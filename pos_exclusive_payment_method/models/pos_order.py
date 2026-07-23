from odoo import fields, models, _
from odoo.tools import float_compare, float_is_zero


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _exclusive_change_payment_method(self, order):
        """Payment method for the auto change line when the first payment is exclusive.

        Uses the payment that caused overpayment when there are several lines; otherwise
        mirrors the first non-change payment method.
        """
        payments = order.payment_ids.filtered(lambda p: not p.is_change).sorted("id")
        if not payments:
            return False

        first_method = payments[0].payment_method_id
        if not first_method.exclusive_payment_method:
            return False

        order._compute_prices()
        amount_total = order.amount_total
        currency = order.currency_id
        running = 0.0
        change_method = first_method
        for payment in payments:
            running += payment.amount
            if float_compare(running, amount_total, precision_rounding=currency.rounding) > 0:
                change_method = payment.payment_method_id
                break
        return change_method

    def _process_payment_lines(self, pos_order, order, pos_session, draft):
        prec_acc = order.currency_id.decimal_places

        order.write({"amount_paid": order._compute_amount_paid()})

        if not draft and not float_is_zero(pos_order.get("amount_return", 0), prec_acc):
            change_method = order._exclusive_change_payment_method(order)
            if change_method:
                order.add_payment(
                    {
                        "name": _("return"),
                        "pos_order_id": order.id,
                        "amount": pos_order["amount_return"],
                        "payment_date": fields.Datetime.now(),
                        "payment_method_id": change_method.id,
                        "is_change": True,
                    }
                )
                order._compute_prices()
                return

        return super()._process_payment_lines(pos_order, order, pos_session, draft)
