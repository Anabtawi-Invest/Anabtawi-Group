# -*- coding: utf-8 -*-
from odoo import models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    def _is_product_in_pricelist(self, product):
        self.ensure_one()
        if not product:
            return True

        items = self.item_ids
        if not items:
            return False

        if items.filtered(lambda item: item.applied_on == "3_global"):
            return True

        category_ids = set()
        category = product.categ_id
        while category:
            category_ids.add(category.id)
            category = category.parent_id

        for item in items:
            if item.applied_on == "0_product_variant" and item.product_id == product:
                return True
            if item.applied_on == "1_product" and item.product_tmpl_id == product.product_tmpl_id:
                return True
            if item.applied_on == "2_product_category" and item.categ_id.id in category_ids:
                return True
        return False

    def _get_products_not_in_pricelist(self, products):
        self.ensure_one()
        products = products.filtered(lambda product: product)
        return products.filtered(lambda product: not self._is_product_in_pricelist(product))
