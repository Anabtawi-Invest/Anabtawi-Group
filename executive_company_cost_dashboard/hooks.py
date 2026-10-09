# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Classify the chart of accounts and the analytic accounts once, right after install."""
    try:
        with env.cr.savepoint():
            result = env["ceo.smart.scanner.wizard"].sudo()._scan(overwrite=False)
        _logger.info("Executive Company Cost Dashboard initial scan: %s", result)
    except Exception:  # never block the installation
        _logger.exception("Executive Company Cost Dashboard: initial scan failed, run it from Configuration.")
