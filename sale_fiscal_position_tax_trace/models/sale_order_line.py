import logging

from odoo import models


_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _compute_tax_ids(self):
        super()._compute_tax_ids()
        for line in self.filtered(lambda l: not l.display_type and l.product_id):
            source_taxes = line.product_id.taxes_id._filter_taxes_by_company(line.company_id)
            _logger.info(
                "[FP TAX TRACE] SO %s line %s product %s fiscal_position %s mapped taxes %s -> %s",
                line.order_id.name or line.order_id.id,
                line.id or "new",
                line.product_id.display_name,
                line.order_id.fiscal_position_id.display_name or line.order_id.fiscal_position_id.id or "none",
                source_taxes.ids,
                line.tax_ids.ids,
            )
