# -*- coding: utf-8 -*-
import base64
import io

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None


class ProductLastBillPriceWizard(models.TransientModel):
    _name = 'product.last.bill.price.wizard'
    _description = 'Export Products Last Vendor Bill Price'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    only_with_bill = fields.Boolean(
        string='Only Products With a Vendor Bill',
        default=False,
        help='If checked, products that were never billed are excluded from the export.',
    )
    include_archived = fields.Boolean(
        string='Include Archived Products',
        default=False,
    )
    file_data = fields.Binary(string='File', readonly=True)
    filename = fields.Char(string='Filename', readonly=True)

    def action_export_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The Python library 'xlsxwriter' is required to export Excel files."))

        rows = self._prepare_rows()
        if not rows:
            raise UserError(_('No products found for the selected filters.'))

        xlsx_bytes = self._build_xlsx(rows)
        fname = f"Product_Last_Bill_Price_{fields.Date.context_today(self)}.xlsx"
        self.write({
            'file_data': base64.b64encode(xlsx_bytes),
            'filename': fname,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content/?model={self._name}'
                f'&id={self.id}&field=file_data&filename={fname}&download=true'
            ),
            'target': 'self',
        }

    def _prepare_rows(self):
        self.ensure_one()
        last_prices = self._get_last_bill_prices()

        product_domain = [('company_id', 'in', [False, self.company_id.id])]
        if not self.include_archived:
            product_domain.append(('active', '=', True))
        if self.only_with_bill:
            product_domain.append(('id', 'in', list(last_prices.keys()) or [0]))

        products = self.env['product.product'].with_context(active_test=False).search(
            product_domain, order='default_code, name, id'
        )

        rows = []
        for product in products:
            info = last_prices.get(product.id) or {}
            rows.append({
                'default_code': product.default_code or '',
                'name': product.display_name,
                'barcode': product.barcode or '',
                'uom': product.uom_id.name or '',
                'price_unit': info.get('price_unit'),
                'currency': info.get('currency') or '',
                'bill_date': info.get('bill_date') or '',
                'bill_number': info.get('bill_number') or '',
                'po_number': info.get('po_number') or '',
                'vendor': info.get('vendor') or '',
            })
        return rows

    def _get_last_bill_prices(self):
        """Map product_id -> last posted vendor bill line info (company-aware)."""
        self.ensure_one()
        self.env.cr.execute(
            """
            SELECT DISTINCT ON (aml.product_id)
                aml.product_id,
                aml.price_unit,
                am.invoice_date,
                am.name AS bill_number,
                po.name AS po_number,
                rp.name AS vendor_name,
                rc.name AS currency_name
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            LEFT JOIN purchase_order_line pol ON pol.id = aml.purchase_line_id
            LEFT JOIN purchase_order po ON po.id = pol.order_id
            LEFT JOIN res_partner rp ON rp.id = am.partner_id
            LEFT JOIN res_currency rc ON rc.id = am.currency_id
            WHERE am.move_type = 'in_invoice'
              AND am.state = 'posted'
              AND am.company_id = %s
              AND aml.display_type = 'product'
              AND aml.product_id IS NOT NULL
            ORDER BY aml.product_id,
                     am.invoice_date DESC NULLS LAST,
                     am.id DESC,
                     aml.id DESC
            """,
            (self.company_id.id,),
        )
        result = {}
        for row in self.env.cr.dictfetchall():
            result[row['product_id']] = {
                'price_unit': row['price_unit'],
                'bill_date': row['invoice_date'] or '',
                'bill_number': row['bill_number'] or '',
                'po_number': row['po_number'] or '',
                'vendor': row['vendor_name'] or '',
                'currency': row['currency_name'] or '',
            }
        return result

    def _build_xlsx(self, rows):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(_('Last Bill Price'))
        sheet.freeze_panes(1, 0)

        price_digits = self.env['decimal.precision'].precision_get('Product Price')
        price_num_format = '#,##0' if price_digits <= 0 else f'#,##0.{"0" * price_digits}'

        header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
        })
        text_style = workbook.add_format({'border': 1})
        date_style = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})
        number_style = workbook.add_format({'border': 1, 'num_format': price_num_format})

        headers = [
            _('Internal Reference'),
            _('Product'),
            _('Barcode'),
            _('UoM'),
            _('Last Bill Price'),
            _('Currency'),
            _('Bill Date'),
            _('Bill Number'),
            _('PO Number'),
            _('Vendor'),
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_style)

        for row_idx, row in enumerate(rows, start=1):
            sheet.write(row_idx, 0, row['default_code'], text_style)
            sheet.write(row_idx, 1, row['name'], text_style)
            sheet.write(row_idx, 2, row['barcode'], text_style)
            sheet.write(row_idx, 3, row['uom'], text_style)
            if row['price_unit'] is None:
                sheet.write(row_idx, 4, '', text_style)
            else:
                sheet.write_number(row_idx, 4, row['price_unit'], number_style)
            sheet.write(row_idx, 5, row['currency'], text_style)
            if row['bill_date']:
                sheet.write_datetime(row_idx, 6, row['bill_date'], date_style)
            else:
                sheet.write(row_idx, 6, '', text_style)
            sheet.write(row_idx, 7, row['bill_number'], text_style)
            sheet.write(row_idx, 8, row['po_number'], text_style)
            sheet.write(row_idx, 9, row['vendor'], text_style)

        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 1, 40)
        sheet.set_column(2, 2, 16)
        sheet.set_column(3, 3, 10)
        sheet.set_column(4, 4, 16)
        sheet.set_column(5, 5, 10)
        sheet.set_column(6, 6, 14)
        sheet.set_column(7, 7, 18)
        sheet.set_column(8, 8, 18)
        sheet.set_column(9, 9, 30)

        workbook.close()
        return output.getvalue()
