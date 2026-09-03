import json
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    def _send_l10n_jo_edi_request(self, params, headers):
        try:
            return super()._send_l10n_jo_edi_request(params, headers)
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
