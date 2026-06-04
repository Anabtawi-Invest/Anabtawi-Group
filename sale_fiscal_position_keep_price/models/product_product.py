import logging

from odoo import models


_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _get_tax_included_unit_price_from_price(
        self,
        product_price_unit,
        product_taxes,
        fiscal_position=None,
        product_taxes_after_fp=None,
    ):
        mapped_taxes = product_taxes_after_fp
        if fiscal_position and mapped_taxes is None:
            mapped_taxes = fiscal_position.map_tax(product_taxes)

        if fiscal_position and fiscal_position.keep_pricelist_price_after_tax_mapping:
            _logger.info(
                "[KEEP PRICE TRACE] Keep enabled for product %s (%s): input price=%s, taxes=%s, mapped_taxes=%s, returned=%s",
                self.display_name,
                self.id,
                product_price_unit,
                product_taxes.ids,
                mapped_taxes.ids if mapped_taxes else [],
                product_price_unit,
            )
            return product_price_unit

        result = super()._get_tax_included_unit_price_from_price(
            product_price_unit=product_price_unit,
            product_taxes=product_taxes,
            fiscal_position=fiscal_position,
            product_taxes_after_fp=mapped_taxes,
        )
        if fiscal_position:
            _logger.info(
                "[KEEP PRICE TRACE] Keep disabled for product %s (%s): input price=%s, taxes=%s, mapped_taxes=%s, returned=%s",
                self.display_name,
                self.id,
                product_price_unit,
                product_taxes.ids,
                mapped_taxes.ids if mapped_taxes else [],
                result,
            )
        return result
