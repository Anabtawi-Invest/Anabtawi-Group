# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Close active pledges whose pledge product was already refunded by a standard POS refund."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Pledge = env["pos.advance.order.pledge"]
    orders = Pledge.search(
        [("state", "=", "active"), ("pos_order_id", "!=", False)]
    ).pos_order_id.filtered(lambda o: o.lines.refund_orderline_ids)
    closed = Pledge._sync_pledges_with_pos_refunds(orders)
    _logger.info(
        "[PLEDGE] Closed %s active pledge(s) already refunded via POS refund orders: %s",
        len(closed),
        closed.mapped("pos_order_id.name"),
    )
