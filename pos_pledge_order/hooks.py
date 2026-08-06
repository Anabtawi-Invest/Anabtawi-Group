# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Log module readiness and ensure one site service record per company."""
    try:
        companies = env["res.company"].sudo().search([])
        for company in companies:
            env["pos.site.service.menu"].with_company(company).get_company_settings(company.id)

        module = env["ir.module.module"].search([("name", "=", "pos_pledge_order")], limit=1)
        version = module.latest_version if module else "unknown"
        menu_count = env["pos.site.service.menu"].sudo().search_count([])
        line_count = env["pos.site.service.product.line"].sudo().search_count([])
        _logger.info(
            "[POS_PLEDGE_ORDER] Module loaded successfully (version=%s). "
            "Site service menus=%s, product lines=%s.",
            version,
            menu_count,
            line_count,
        )
    except Exception:
        _logger.exception(
            "[POS_PLEDGE_ORDER] post_init_hook failed — check Site Service models/tables."
        )
        raise
