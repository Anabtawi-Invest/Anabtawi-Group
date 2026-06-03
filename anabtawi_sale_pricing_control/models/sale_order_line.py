# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError

GROUP_PRICE_OVERRIDE_XMLID = "anabtawi_sale_pricing_control.group_sales_price_override"
GROUP_PRICE_OVERRIDE_NAME = "Sales Price Override"


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _user_can_override_unit_price(self):
        return self.env.user.has_group(GROUP_PRICE_OVERRIDE_XMLID)

    def _skip_price_override_validation(self):
        context = self.env.context
        return (
            context.get("skip_price_override_validation")
            or context.get("sale_write_from_compute")
            or context.get("force_price_recomputation")
        )

    def _get_expected_pricelist_price_unit(self):
        self.ensure_one()
        if self.display_type or not self.order_id or not self.product_id or not self.order_id.pricelist_id:
            return self.price_unit

        line = self.with_company(self.company_id)
        price = line._get_display_price()
        product_taxes = line.product_id.taxes_id._filter_taxes_by_company(line.company_id)
        return line.product_id._get_tax_included_unit_price_from_price(
            price,
            product_taxes=product_taxes,
            fiscal_position=line.order_id.fiscal_position_id,
        )

    def _validate_manual_price_override(self):
        if self._skip_price_override_validation() or self._user_can_override_unit_price():
            return

        for line in self.filtered(lambda sale_line: not sale_line.display_type and sale_line.product_id):
            expected_price = line._get_expected_pricelist_price_unit()
            currency = line.currency_id or line.order_id.currency_id or line.company_id.currency_id
            if currency.compare_amounts(line.price_unit, expected_price):
                raise ValidationError(_(
                    "You are not allowed to manually modify Unit Price.\n"
                    "To perform this action, your user must belong to '%(group)s'."
                ) % {
                    "group": GROUP_PRICE_OVERRIDE_NAME,
                })

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._validate_manual_price_override()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if {"price_unit", "technical_price_unit"}.intersection(vals):
            self._validate_manual_price_override()
        return result
