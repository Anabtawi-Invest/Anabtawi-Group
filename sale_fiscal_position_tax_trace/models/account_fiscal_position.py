import logging

from odoo import models


_logger = logging.getLogger(__name__)


class AccountFiscalPosition(models.Model):
    _inherit = "account.fiscal.position"

    def map_tax(self, taxes):
        mapped_taxes = super().map_tax(taxes)
        if self:
            _logger.info(
                "[FP TAX TRACE] Fiscal position %s (%s) mapped taxes %s -> %s",
                self.display_name,
                self.id,
                taxes.ids,
                mapped_taxes.ids,
            )
        return mapped_taxes
