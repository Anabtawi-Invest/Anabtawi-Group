import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        for order in self.filtered(lambda record: record.state == "paid"):
            order._ensure_gift_zero_hospitality_payment()
        return result

    def _ensure_gift_zero_hospitality_payment(self):
        self.ensure_one()
        if not self.lines.filtered("is_gift"):
            return

        hospitality_payment_method = self.config_id.payment_method_ids.filtered(
            lambda method: "hospitality" in (method.name or "").lower()
        )[:1]
        if not hospitality_payment_method:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Order %s has gift lines but no hospitality payment method found in POS config %s",
                self.name,
                self.config_id.display_name,
            )
            return

        existing = self.payment_ids.filtered(
            lambda payment: payment.payment_method_id == hospitality_payment_method
            and payment.currency_id.is_zero(payment.amount)
            and not payment.is_change
        )
        if existing:
            return

        self.add_payment(
            {
                "name": _("Hospitality Gift"),
                "pos_order_id": self.id,
                "amount": 0.0,
                "payment_date": fields.Datetime.now(),
                "payment_method_id": hospitality_payment_method.id,
                "is_change": False,
            }
        )
