# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError

GROUP_NO_PRICELIST_XMLID = "anabtawi_sale_pricing_control.group_sales_order_without_pricelist"
GROUP_NO_PRICELIST_NAME = "Sales Order Without Pricelist"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _user_can_bypass_pricelist_validation(self):
        return self.env.user.has_group(GROUP_NO_PRICELIST_XMLID)

    def _get_products_not_in_order_pricelist(self):
        self.ensure_one()
        lines = self.order_line.filtered(lambda line: not line.display_type and line.product_id)
        if not self.pricelist_id or not lines:
            return self.env["product.product"]
        return self.pricelist_id._get_products_not_in_pricelist(lines.mapped("product_id"))

    def _validate_order_pricelist_controls(self):
        if self._user_can_bypass_pricelist_validation():
            return

        for order in self:
            if not order.pricelist_id:
                raise ValidationError(_(
                    "A valid Pricelist is required on Sales Orders.\n"
                    "To bypass this rule, your user must belong to the '%s' group."
                ) % GROUP_NO_PRICELIST_NAME)

            invalid_products = order._get_products_not_in_order_pricelist()
            if invalid_products:
                product_names = ", ".join(invalid_products.mapped("display_name"))
                raise ValidationError(_(
                    "The following products are not included in the selected Pricelist '%(pricelist)s':\n"
                    "%(products)s\n\n"
                    "To bypass this rule, your user must belong to the '%(group)s' group."
                ) % {
                    "pricelist": order.pricelist_id.display_name,
                    "products": product_names,
                    "group": GROUP_NO_PRICELIST_NAME,
                })

    @api.constrains("pricelist_id", "partner_id", "order_line", "order_line.product_id")
    def _check_order_pricelist_controls(self):
        self._validate_order_pricelist_controls()

    def action_confirm(self):
        self._validate_order_pricelist_controls()
        return super().action_confirm()

    @api.onchange("pricelist_id")
    def _onchange_pricelist_id_recompute_existing_lines(self):
        for order in self:
            if order.pricelist_id and order.order_line:
                order.with_context(skip_price_override_validation=True)._recompute_prices()
