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
