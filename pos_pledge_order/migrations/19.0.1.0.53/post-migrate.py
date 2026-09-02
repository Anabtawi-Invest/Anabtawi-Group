# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fix pledge rows corrupted by the old product-refund return flow."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = 'pos_advance_order_pledge'
         LIMIT 1
        """
    )
    if not cr.fetchone():
        return

    # Active pledges must not stay linked to REFUND pos orders.
    cr.execute(
        """
        UPDATE pos_advance_order_pledge pl
           SET pos_order_id = po.refunded_order_id,
               return_pos_order_id = NULL
          FROM pos_order po
         WHERE pl.pos_order_id = po.id
           AND pl.state = 'active'
           AND po.is_refund IS TRUE
           AND po.refunded_order_id IS NOT NULL
        """
    )
    relinked = cr.rowcount
    if relinked:
        _logger.info("[PLEDGE] Relinked %s active pledge(s) from REFUND orders to origin orders.", relinked)

    cr.execute(
        """
        UPDATE pos_advance_order_pledge
           SET pledge_qty = ABS(pledge_qty),
               return_pos_order_id = NULL
         WHERE state = 'active'
           AND pledge_qty < 0
        """
    )
    fixed_qty = cr.rowcount
    if fixed_qty:
        _logger.info("[PLEDGE] Fixed negative pledge_qty on %s active pledge row(s).", fixed_qty)

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'pos_order'
           AND column_name = 'pledge_deposit_move_id'
         LIMIT 1
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            UPDATE pos_advance_order_pledge pl
               SET pledge_move_id = o.pledge_deposit_move_id
              FROM pos_order o
             WHERE pl.pos_order_id = o.id
               AND pl.state = 'active'
               AND (pl.pledge_move_id IS NULL OR pl.pledge_move_id != o.pledge_deposit_move_id)
               AND o.pledge_deposit_move_id IS NOT NULL
            """
        )
        linked = cr.rowcount
        if linked:
            _logger.info("[PLEDGE] Backfilled pledge_move_id on %s active pledge row(s).", linked)
