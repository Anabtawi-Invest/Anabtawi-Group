import json
import logging

import requests

from odoo import models

_logger = logging.getLogger(__name__)

JOFOTARA_URL = "https://backend.jofotara.gov.jo/core/invoices/"


class ResCompany(models.Model):
    _inherit = "res.company"

    def _send_l10n_jo_edi_request(self, params, headers):
        timeout = self.env.context.get("jofotara_request_timeout")
        if not timeout:
            return super()._send_l10n_jo_edi_request(params, headers)
        return self._send_l10n_jo_edi_request_with_timeout(params, headers, timeout)

    def _send_l10n_jo_edi_request_with_timeout(self, params, headers, timeout):
        """Same JoFotara call as l10n_jo_edi, with a caller-chosen timeout."""
        self.ensure_one()
        if self.l10n_jo_edi_demo_mode:
            return {"EINV_QR": "Demo JoFotara QR"}

        try:
            response = requests.post(
                JOFOTARA_URL,
                json=params,
                headers=headers,
                timeout=timeout,
            )
        except requests.exceptions.Timeout:
            _logger.warning(
                "JoFotara timed out after %ss for company %s",
                timeout,
                self.display_name,
            )
            return {"error": self.env._("Request timeout! Please try again.")}
        except requests.exceptions.RequestException as error:
            _logger.warning(
                "JoFotara request failed for company %s: %s",
                self.display_name,
                error,
            )
            return {"error": self.env._("Invalid request: %s", error)}

        if not response.ok:
            content = response.content.decode()
            if response.status_code == 403:
                content = self.env._(
                    "Access forbidden. Please verify your JoFotara credentials."
                )
            return {"error": self.env._("Request failed: %s", content)}

        try:
            return response.json()
        except json.JSONDecodeError:
            _logger.warning(
                "JoFotara returned an empty or invalid JSON response for company %s",
                self.display_name,
            )
            return {
                "error": self.env._(
                    "JoFotara returned an empty or invalid response. "
                    "Please try again later."
                ),
            }
