import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    AdvanceOrder = env["pos.advance.order"].sudo()
    site_service_orders = AdvanceOrder.search([("site_service", "=", True)])
    if not site_service_orders:
        return

    PosOrder = env["pos.order"].sudo()
    pos_orders = PosOrder.search([
        ("advance_order_id", "in", site_service_orders.ids),
        ("pledge_deposit_move_id", "!=", False),
    ])
    if not pos_orders:
        return

    _logger.info(
        "[PLEDGE] Reversing %s erroneous pledge deposit move(s) on site service POS order(s).",
        len(pos_orders),
    )
    for order in pos_orders:
        move = order.pledge_deposit_move_id
        if not move or move.state != "posted":
            order.write({"pledge_deposit_move_id": False})
            continue
        try:
            reverse = move._reverse_moves(default_values_list=[{
                "ref": f"Site service pledge cleanup - {order.name}",
            }])
            if reverse:
                reverse.action_post()
        except Exception:
            _logger.exception(
                "[PLEDGE] Failed to reverse pledge deposit move %s for order %s",
                move.id,
                order.name,
            )
            continue
        order.write({
            "pledge_deposit_move_id": False,
            "total_pledge_amount": 0.0,
            "pledge_product_qty": 0,
        })
        if "pledge_snapshot_product_ids" in PosOrder._fields:
            order.write({"pledge_snapshot_product_ids": [(5, 0, 0)]})

    sessions = pos_orders.mapped("session_id")
    if sessions and hasattr(sessions, "_invalidate_open_sessions_cash_balance"):
        sessions._invalidate_open_sessions_cash_balance()
