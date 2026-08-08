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
    if "total_pledge_amount" not in PosOrder._fields:
        return

    pos_orders = PosOrder.search([("advance_order_id", "in", site_service_orders.ids)])
    if pos_orders:
        _logger.info(
            "[PLEDGE] Resetting pledge closing fields on %s POS order(s) for site service advances.",
            len(pos_orders),
        )
        pos_orders.write({
            "total_pledge_amount": 0.0,
            "pledge_product_qty": 0,
        })
        if "pledge_snapshot_product_ids" in PosOrder._fields:
            pos_orders.write({"pledge_snapshot_product_ids": [(5, 0, 0)]})

    site_service_orders._sync_pledge_lines()

    sessions = pos_orders.mapped("session_id")
    if sessions and hasattr(sessions, "_invalidate_open_sessions_cash_balance"):
        sessions._invalidate_open_sessions_cash_balance()
