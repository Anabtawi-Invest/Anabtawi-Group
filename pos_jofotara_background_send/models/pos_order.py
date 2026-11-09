import logging

from odoo import models

_logger = logging.getLogger(__name__)

# Keep the cashier waiting only long enough for a healthy JoFotara reply.
POS_PAYMENT_TIMEOUT = 8
# Background retries can wait longer without blocking the POS screen.
BACKGROUND_TIMEOUT = 20
CRON_BATCH_SIZE = 5


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        # The Jordan module sends to JoFotara inside this call. Limit that wait
        # so a slow portal cannot hold the payment screen for 50 seconds.
        return super(
            PosOrder,
            self.with_context(jofotara_request_timeout=POS_PAYMENT_TIMEOUT),
        ).action_pos_order_paid()

    def _cron_retry_jofotara_pos_orders(self):
        """Resend paid orders that JoFotara did not accept yet."""
        orders = self.search(
            [
                ("l10n_jo_edi_pos_state", "=", "to_send"),
                ("state", "in", ("paid", "done", "invoiced")),
            ],
            limit=CRON_BATCH_SIZE,
            order="date_order, id",
        )
        for order in orders:
            if not order.l10n_jo_edi_pos_enabled or order.country_code != "JO":
                continue
            try:
                with self.env.cr.savepoint():
                    order.with_context(
                        jofotara_request_timeout=BACKGROUND_TIMEOUT
                    )._l10n_jo_edi_send()
            except Exception:
                _logger.exception(
                    "JoFotara background send failed for POS order %s",
                    order.name,
                )
