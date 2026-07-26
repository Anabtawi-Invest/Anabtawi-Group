# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT id, name
        FROM pos_cake_order
        WHERE production_id IS NULL
          AND state != 'cancelled'
        """
    )
    rows = cr.fetchall()
    if not rows:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["pos.cake.order"].browse([row[0] for row in rows])
    for order in orders:
        try:
            production = order._create_manufacturing_order()
            order.production_id = production.id
            _logger.info("Backfilled MO %s for cake order %s", production.name, order.name)
        except Exception as error:
            _logger.warning(
                "Could not backfill MO for cake order %s: %s",
                order.name,
                error,
            )
