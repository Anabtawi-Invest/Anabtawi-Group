import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    AdvanceOrder = env["pos.advance.order"].sudo()
    site_service_orders = AdvanceOrder.search([("site_service", "=", True)])
    if not site_service_orders:
        return
    _logger.info(
        "[ADVANCE_ORDER] Clearing pledge lines on %s site service advance order(s).",
        len(site_service_orders),
    )
    site_service_orders._sync_pledge_lines()

    PosOrder = env["pos.order"].sudo()
    if "total_pledge_amount" in PosOrder._fields:
        pos_orders = PosOrder.search([("advance_order_id", "in", site_service_orders.ids)])
        if pos_orders:
            _logger.info(
                "[ADVANCE_ORDER] Clearing pledge snapshot on %s POS order(s) for site service advances.",
                len(pos_orders),
            )
            pos_orders.write({"total_pledge_amount": 0.0})
            sessions = pos_orders.mapped("session_id")
            if sessions and hasattr(sessions, "_invalidate_open_sessions_cash_balance"):
                sessions._invalidate_open_sessions_cash_balance()
