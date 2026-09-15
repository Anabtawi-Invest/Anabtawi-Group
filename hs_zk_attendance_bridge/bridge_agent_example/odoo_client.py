# -*- coding: utf-8 -*-
"""HTTP client that pushes attendance records to the existing Odoo bridge endpoint."""

from __future__ import annotations

import logging

import requests

_logger = logging.getLogger(__name__)


class OdooBridgeClient:
    def __init__(self, odoo_url: str, timeout: int = 60):
        self.odoo_url = odoo_url.rstrip("/")
        self.timeout = timeout

    def push(
        self,
        *,
        token: str,
        device_identifier: str,
        records: list[dict],
        source: str,
    ) -> dict:
        payload = {
            "token": token,
            "device_identifier": device_identifier,
            "source": source,
            "records": records,
        }
        url = f"{self.odoo_url}/hs_zk_attendance_bridge/push"
        _logger.info("Sending %s records to Odoo (%s)", len(records), device_identifier)
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", True):
            raise RuntimeError(f"Odoo request failed: {body.get('error') or body}")
        _logger.info("Odoo accepted batch for %s: %s", device_identifier, body.get("results") or body)
        return body
