import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _l10n_jo_edi_send(self):
        try:
            return super()._l10n_jo_edi_send()
        except Exception as error:
            _logger.exception(
                "JoFotara submission failed for POS order(s) %s",
                ", ".join(self.mapped("name")),
            )
            error_message = str(error)
            for order in self:
                order.write(
                    {
                        "l10n_jo_edi_pos_state": "to_send",
                        "l10n_jo_edi_pos_error": error_message,
                        "to_invoice": False,
                    }
                )
            return error_message
