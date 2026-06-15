import logging

from odoo import fields, models


_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_display_price_ignore_combo(self):
        price = super()._get_display_price_ignore_combo()
        if self.product_id:
            _logger.info(
                "[KEEP PRICE TRACE] Display price from pricelist for SO %s line %s product %s (%s): display_price=%s pricelist=%s",
                self.order_id.name or self.order_id.id or "new",
                self.id or "new",
                self.product_id.display_name,
                self.product_id.id,
                price,
                self.order_id.pricelist_id.display_name if self.order_id else "none",
            )
        return price

    def _reset_price_unit(self):
        for line in self:
            if line.product_id and line.order_id:
                display_price = line._get_display_price()
                source_taxes = line.product_id.taxes_id._filter_taxes_by_company(line.company_id)
                mapped_taxes = line.order_id.fiscal_position_id.map_tax(source_taxes)
                _logger.info(
                    "[KEEP PRICE TRACE] Before reset SO %s line %s product %s (%s): display_price=%s source_taxes=%s mapped_taxes=%s fpos=%s keep=%s",
                    line.order_id.name or line.order_id.id or "new",
                    line.id or "new",
                    line.product_id.display_name,
                    line.product_id.id,
                    display_price,
                    source_taxes.ids,
                    mapped_taxes.ids,
                    line.order_id.fiscal_position_id.display_name or "none",
                    bool(line.order_id.fiscal_position_id.keep_pricelist_price_after_tax_mapping),
                )

        res = super()._reset_price_unit()

        for line in self:
            if line.product_id and line.order_id:
                _logger.info(
                    "[KEEP PRICE TRACE] After reset SO %s line %s product %s (%s): price_unit=%s technical_price_unit=%s taxes_on_line=%s",
                    line.order_id.name or line.order_id.id or "new",
                    line.id or "new",
                    line.product_id.display_name,
                    line.product_id.id,
                    line.price_unit,
                    line.technical_price_unit,
                    line.tax_ids.ids,
                )
        return res


class PosOrder(models.Model):
    _inherit = "pos.order"

    manual_fiscal_position_applied = fields.Boolean(
        copy=False,
        help="True when cashier manually selected fiscal position in POS.",
    )

    def _process_saved_order(self, draft):
        result = super()._process_saved_order(draft)
        for order in self:
            if draft or order.state != "paid":
                continue
            if not order.manual_fiscal_position_applied:
                continue
            if not order.partner_id or not order.fiscal_position_id:
                continue
            if order.fiscal_position_id.keep_pricelist_price_after_tax_mapping:
                order.partner_id.sudo().write({
                    "fiscal_position_id": order.fiscal_position_id.id,
                })
        return result
