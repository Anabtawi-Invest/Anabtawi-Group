# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _get_po_line_uom(self):
        """Return the PO line UoM across Odoo field renames."""
        self.ensure_one()
        for fname in ('uom_id', 'product_uom', 'product_uom_id'):
            if fname in self._fields:
                return self[fname] or self.product_id.uom_id
        return self.product_id.uom_id

    def _get_last_bill_price_unit(self):
        """Return the unit price from the latest posted vendor bill for this product.

        Searches any vendor in the same company. Returns 0.0 when no bill exists.
        Converts bill currency and UoM to the PO line currency and UoM.
        """
        self.ensure_one()
        if not self.product_id or not self.company_id:
            _logger.info(
                "PLBP skip lookup: product_id=%s company_id=%s",
                self.product_id.id if self.product_id else False,
                self.company_id.id if self.company_id else False,
            )
            return 0.0

        self.env.cr.execute(
            """
            SELECT
                aml.price_unit,
                am.currency_id,
                aml.product_uom_id,
                am.invoice_date,
                am.name AS bill_name,
                aml.display_type
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.move_type = 'in_invoice'
              AND am.state = 'posted'
              AND am.company_id = %s
              AND aml.product_id = %s
              AND aml.display_type IS DISTINCT FROM 'line_section'
              AND aml.display_type IS DISTINCT FROM 'line_note'
            ORDER BY
                am.invoice_date DESC NULLS LAST,
                am.id DESC,
                aml.id DESC
            LIMIT 1
            """,
            (self.company_id.id, self.product_id.id),
        )
        row = self.env.cr.dictfetchone()
        if not row:
            _logger.info(
                "PLBP no bill: product=%s (%s) company=%s",
                self.product_id.default_code or self.product_id.id,
                self.product_id.id,
                self.company_id.id,
            )
            return 0.0

        price_unit = row['price_unit'] or 0.0
        bill_currency = self.env['res.currency'].browse(row['currency_id'])
        bill_uom = (
            self.env['uom.uom'].browse(row['product_uom_id'])
            if row['product_uom_id']
            else self.product_id.uom_id
        )
        po_uom = self._get_po_line_uom()
        conversion_date = row['invoice_date'] or self.date_order or fields.Date.context_today(self)

        _logger.info(
            "PLBP found bill=%s date=%s raw_price=%s display_type=%s "
            "bill_currency=%s bill_uom=%s po_uom=%s product=%s company=%s",
            row.get('bill_name'),
            row.get('invoice_date'),
            price_unit,
            row.get('display_type'),
            bill_currency.name if bill_currency else None,
            bill_uom.name if bill_uom else None,
            po_uom.name if po_uom else None,
            self.product_id.default_code or self.product_id.id,
            self.company_id.id,
        )

        if bill_currency and self.currency_id and bill_currency != self.currency_id:
            price_unit = bill_currency._convert(
                price_unit,
                self.currency_id,
                self.company_id,
                conversion_date,
                False,
            )

        if bill_uom and po_uom and bill_uom != po_uom:
            price_unit = bill_uom._compute_price(price_unit, po_uom)

        price_unit = float_round(
            price_unit,
            precision_digits=max(
                self.currency_id.decimal_places if self.currency_id else 2,
                self.env['decimal.precision'].precision_get('Product Price'),
            ),
        )
        _logger.info("PLBP converted price=%s", price_unit)
        return price_unit

    def _apply_last_bill_price(self, source='compute'):
        """Apply last bill price; return True if applied."""
        for line in self:
            if not line.product_id:
                _logger.info("PLBP %s skip: no product", source)
                continue
            if line.invoice_lines:
                _logger.info(
                    "PLBP %s skip: already invoiced product=%s",
                    source,
                    line.product_id.default_code or line.product_id.id,
                )
                continue
            if not line.company_id:
                _logger.info(
                    "PLBP %s skip: no company_id product=%s",
                    source,
                    line.product_id.default_code or line.product_id.id,
                )
                continue
            if self.env.context.get('skip_uom_conversion'):
                _logger.info("PLBP %s skip: skip_uom_conversion context", source)
                continue
            if line.technical_price_unit != line.price_unit:
                _logger.info(
                    "PLBP %s skip: manual edit technical=%s price=%s product=%s",
                    source,
                    line.technical_price_unit,
                    line.price_unit,
                    line.product_id.default_code or line.product_id.id,
                )
                continue

            before = line.price_unit
            price_unit = line._get_last_bill_price_unit()
            line.discount = 0.0
            line.price_unit = line.technical_price_unit = price_unit
            _logger.info(
                "PLBP %s applied: product=%s before=%s after=%s company=%s partner=%s",
                source,
                line.product_id.default_code or line.product_id.id,
                before,
                price_unit,
                line.company_id.id,
                line.order_id.partner_id.id if line.order_id else False,
            )
        return True

    # Include product_id so price refreshes on product select.
    # Do not depend on uom_id (missing on some staging builds).
    @api.depends('product_id', 'product_qty', 'company_id', 'order_id.partner_id')
    def _compute_price_unit_and_date_planned_and_name(self):
        _logger.info(
            "PLBP compute start: products=%s",
            self.mapped(lambda l: l.product_id.default_code or l.product_id.id),
        )
        super()._compute_price_unit_and_date_planned_and_name()
        self._apply_last_bill_price(source='compute')

    @api.onchange('product_id')
    def onchange_product_id(self):
        res = super().onchange_product_id()
        _logger.info(
            "PLBP onchange_product_id: product=%s price_after_super=%s technical=%s",
            self.product_id.default_code if self.product_id else False,
            self.price_unit,
            self.technical_price_unit,
        )
        # Force apply after core onchange (UI path).
        if self.product_id and self.company_id:
            # Reset technical so a previous manual price does not block re-select.
            if self.technical_price_unit != self.price_unit and self.price_unit == 0.0:
                self.technical_price_unit = 0.0
            self._apply_last_bill_price(source='onchange')
        return res
