# -*- coding: utf-8 -*-
"""Built-in MEPS mock gateway for Odoo.sh / staging (no external tunnel needed).

Enable in Settings → Point of Sale → MEPS Connection, then set Gateway URL to:
  https://<your-db>.odoo.com/pos_meps_terminal/mock
or with a scenario:
  https://<your-db>.odoo.com/pos_meps_terminal/mock?scenario=decline
"""
import logging
import time

from odoo import http
from odoo.http import request

from odoo.addons.pos_meps_terminal.meps_mock_payload import (
    ICP_ENABLE_MOCK,
    amount_from_body,
    build_mock_response,
    detect_operation,
    normalize_scenario,
)

_logger = logging.getLogger(__name__)


class PosMepsMockController(http.Controller):

    def _mock_enabled(self):
        return request.env["ir.config_parameter"].sudo().get_param(ICP_ENABLE_MOCK) == "True"

    @http.route(
        ["/pos_meps_terminal/mock", "/pos_meps_terminal/mock/<path:unused>"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
        save_session=False,
    )
    def meps_mock_gateway(self, unused=None, scenario=None, **kwargs):
        if not self._mock_enabled():
            return request.make_response(
                "MEPS mock gateway is disabled. Enable it in Settings → Point of Sale → MEPS Connection.",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=403,
            )

        if request.httprequest.method == "GET":
            body = (
                "MEPS built-in mock gateway is enabled.\n"
                "POST SOAP Sale/Void/Settlement here.\n"
                "Scenarios: success|decline|timeout|fault|http500|bad_xml\n"
                "Example: /pos_meps_terminal/mock?scenario=decline\n"
            )
            return request.make_response(
                body,
                headers=[("Content-Type", "text/plain; charset=utf-8")],
            )

        raw = request.httprequest.get_data() or b""
        soap_action = (request.httprequest.headers.get("SOAPAction") or "").strip().strip('"')
        header_scenario = request.httprequest.headers.get("X-MEPS-Scenario")
        chosen = normalize_scenario(scenario or header_scenario or "success")
        operation = detect_operation(soap_action, raw)
        amount = amount_from_body(raw)

        _logger.info(
            "MEPS mock: op=%s scenario=%s amount=%s action=%r",
            operation,
            chosen,
            amount,
            soap_action,
        )

        status, content_type, payload, sleep_s = build_mock_response(
            chosen, operation, amount, timeout_sleep=12
        )
        if sleep_s:
            _logger.warning("MEPS mock: sleeping %ss for timeout scenario", sleep_s)
            time.sleep(sleep_s)

        return request.make_response(
            payload,
            headers=[("Content-Type", content_type)],
            status=status,
        )
