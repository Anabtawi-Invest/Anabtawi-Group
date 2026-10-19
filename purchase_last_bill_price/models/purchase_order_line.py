# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools.float_utils import float_round


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
            return 0.0

        self.env.cr.execute(
            """
            SELECT
                aml.price_unit,
                am.currency_id,
                aml.product_uom_id,
                am.invoice_date
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

        return float_round(
            price_unit,
            precision_digits=max(
                self.currency_id.decimal_places,
                self.env['decimal.precision'].precision_get('Product Price'),
            ),
        )

    def _compute_price_unit_and_date_planned_and_name(self):
        # Do not redeclare @api.depends: keep core triggers (avoids invalid
        # dependency fields across Odoo versions).
        super()._compute_price_unit_and_date_planned_and_name()
        for line in self:
            # Same early exits as core: skip if already invoiced or manually edited.
            if (
                not line.product_id
                or line.invoice_lines
                or not line.company_id
                or self.env.context.get('skip_uom_conversion')
                or (line.technical_price_unit != line.price_unit)
            ):
                continue
            price_unit = line._get_last_bill_price_unit()
            line.discount = 0.0
            line.price_unit = line.technical_price_unit = price_unit
