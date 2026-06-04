from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _get_tax_included_unit_price_from_price(
        self,
        product_price_unit,
        product_taxes,
        fiscal_position=None,
        product_taxes_after_fp=None,
    ):
        if fiscal_position and fiscal_position.keep_pricelist_price_after_tax_mapping:
            return product_price_unit
        return super()._get_tax_included_unit_price_from_price(
            product_price_unit=product_price_unit,
            product_taxes=product_taxes,
            fiscal_position=fiscal_position,
            product_taxes_after_fp=product_taxes_after_fp,
        )
