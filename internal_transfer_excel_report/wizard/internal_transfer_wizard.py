from datetime import datetime, time, timedelta
import io
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_BARCODE_FONTS = (
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
)


def _barcode_font(size):
    from PIL import ImageFont  # pylint: disable=import-outside-toplevel

    for path in _BARCODE_FONTS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _code128_image(value):
    """Return a Code128 PNG stream for an ASCII reference, or None."""
    if not value or any(ord(char) > 127 for char in value):
        return None

    from PIL import Image, ImageDraw  # pylint: disable=import-outside-toplevel
    from reportlab.graphics.barcode.code128 import Code128  # pylint: disable=import-outside-toplevel

    barcode = Code128(value)
    barcode.validate()
    if not barcode.valid:
        return None
    barcode.encode()
    pattern = barcode.decompose()

    module = 2
    quiet = 10 * module
    bar_height = 70
    text_gap = 4
    padding_y = 6
    font = _barcode_font(14)

    modules = sum(ord(char.upper()) - ord('A') + 1 for char in pattern)
    bars_width = modules * module
    probe = Image.new('RGB', (1, 1))
    probe_draw = ImageDraw.Draw(probe)
    text_left, text_top, text_right, text_bottom = probe_draw.textbbox((0, 0), value, font=font)
    text_width = text_right - text_left
    text_height = text_bottom - text_top

    width = max(bars_width + quiet * 2, text_width + quiet * 2)
    height = padding_y + bar_height + text_gap + text_height + padding_y
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)

    x = (width - bars_width) / 2
    y = padding_y
    for char in pattern:
        bar_px = (ord(char.upper()) - ord('A') + 1) * module
        if char.isupper():
            draw.rectangle([x, y, x + bar_px - 1, y + bar_height - 1], fill='black')
        x += bar_px

    text_x = (width - text_width) / 2 - text_left
    text_y = padding_y + bar_height + text_gap - text_top
    draw.text((text_x, text_y), value, fill='black', font=font)

    stream = io.BytesIO()
    image.save(stream, format='PNG')
    stream.seek(0)
    return stream, width, height


class InternalTransferReportWizard(models.TransientModel):
    _name = 'internal.transfer.report.wizard'
    _description = 'Internal Transfer Report Wizard'

    filter_type = fields.Selection([
        ('week', 'This Week'),
        ('last_month', 'Last Month'),
        ('custom', 'Custom'),
        ('today', 'Today'),
    ], default='week', required=True)

    date_from = fields.Datetime()
    date_to = fields.Datetime()

    all_factory_plan_categories = fields.Boolean(
        string='All Factory Plan Categories',
        default=True,
    )
    factory_plan_category_ids = fields.Many2many(
        'factory.plan.category.option',
        'int_transfer_wiz_fpc_option_rel',
        'wizard_id',
        'option_id',
        string='Factory Plan Categories',
    )
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        required=True,
        domain="[('code', '=', 'internal')]",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        self.env['factory.plan.category.option'].sync_from_products()
        if 'picking_type_id' in fields_list and not res.get('picking_type_id'):
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('company_id', 'in', [self.env.company.id, False]),
            ], limit=1)
            if picking_type:
                res['picking_type_id'] = picking_type.id
        return res

    @api.onchange('all_factory_plan_categories')
    def _onchange_all_factory_plan_categories(self):
        if self.all_factory_plan_categories:
            self.factory_plan_category_ids = [(5, 0, 0)]

    def _get_report_lang(self):
        self.ensure_one()
        return (
            self.env.context.get('lang')
            or self.env.user.lang
            or self.env.company.partner_id.lang
            or 'en_US'
        )

    def _compute_dates(self):
        self.ensure_one()
        today = fields.Date.today()

        if self.filter_type == 'week':
            start_d = today - timedelta(days=today.weekday())
            end_d = start_d + timedelta(days=6)
            start = datetime.combine(start_d, time.min)
            end = datetime.combine(end_d, time.max)

        elif self.filter_type == 'last_month':
            first_day = today.replace(day=1)
            last_month_end = first_day - timedelta(days=1)
            start_d = last_month_end.replace(day=1)
            end_d = last_month_end
            start = datetime.combine(start_d, time.min)
            end = datetime.combine(end_d, time.max)

        elif self.filter_type == 'today':
            start = datetime.combine(today, time.min)
            end = datetime.combine(today, time.max)

        else:
            if not self.date_from or not self.date_to:
                raise UserError(_("Please set both start and end date/time for custom filter."))
            start = fields.Datetime.to_datetime(self.date_from)
            end = fields.Datetime.to_datetime(self.date_to)

        return fields.Datetime.to_string(start), fields.Datetime.to_string(end)

    def _get_factory_plan_category_display(self, product):
        category = product.product_tmpl_id.factory_plan_category
        return category if category else self.env._('Non')

    def _get_move_uom_name(self, move):
        return move.product_uom.display_name or move.product_id.uom_id.display_name or ''

    def _get_factory_plan_category_product_ids(self):
        """Return matching product ids, empty list if none, None if no filter."""
        self.ensure_one()
        if self.all_factory_plan_categories or not self.factory_plan_category_ids:
            return None

        named_categories = self.factory_plan_category_ids.filtered(
            lambda option: not option.is_uncategorized
        ).mapped('name')
        include_uncategorized = bool(
            self.factory_plan_category_ids.filtered('is_uncategorized')
        )

        if named_categories and include_uncategorized:
            product_domain = [
                '|',
                ('factory_plan_category', 'in', named_categories),
                '|',
                ('factory_plan_category', '=', False),
                ('factory_plan_category', '=', ''),
            ]
        elif named_categories:
            product_domain = [('factory_plan_category', 'in', named_categories)]
        else:
            product_domain = [
                '|',
                ('factory_plan_category', '=', False),
                ('factory_plan_category', '=', ''),
            ]

        return self.env['product.product'].search(product_domain).ids

    def _append_factory_plan_category_domain(self, move_domain):
        product_ids = self._get_factory_plan_category_product_ids()
        if product_ids is None:
            return move_domain
        move_domain.append(('product_id', 'in', product_ids or [0]))
        return move_domain

    def _get_base_picking_domain(self):
        self.ensure_one()
        if not self.picking_type_id:
            raise UserError(_("Please select an operation type."))
        date_from_dt, date_to_dt = self._compute_dates()
        return [
            ('picking_type_id', '=', self.picking_type_id.id),
            ('create_date', '>=', date_from_dt),
            ('create_date', '<=', date_to_dt),
        ]

    def _get_sheet1_data(self):
        self.ensure_one()

        picking_domain = self._get_base_picking_domain()
        picking_domain.append(('state', 'not in', ('done', 'cancel')))
        picking_ids = self.env['stock.picking'].search(picking_domain).ids
        if not picking_ids:
            return []

        move_domain = [
            ('picking_id.picking_type_id', '=', self.picking_type_id.id),
            ('picking_id', 'in', picking_ids),
            ('picking_id.state', 'not in', ('done', 'cancel')),
            ('state', 'not in', ('done', 'cancel')),
            ('move_dest_ids', '=', False),
        ]
        move_domain = self._append_factory_plan_category_domain(move_domain)

        moves = self.env['stock.move'].search(
            move_domain,
            order='picking_id, product_id',
        )
        rows = []
        for move in moves:
            picking = move.picking_id
            rows.append({
                'transfer_reference': picking.name or '',
                'product_name': move.product_id.display_name,
                'factory_plan_category': self._get_factory_plan_category_display(move.product_id),
                'created_by': picking.create_uid.display_name or self.env._('Undefined'),
                'creating_date': picking.create_date,
                'demand': move.product_uom_qty,
                'product_uom': self._get_move_uom_name(move),
            })
        return rows

    def _get_sheet2_data(self):
        self.ensure_one()

        picking_domain = self._get_base_picking_domain()
        picking_domain.append(('state', 'not in', ('done', 'cancel')))
        picking_ids = self.env['stock.picking'].search(picking_domain).ids
        if not picking_ids:
            return []

        move_domain = [
            ('picking_id.picking_type_id', '=', self.picking_type_id.id),
            ('picking_id', 'in', picking_ids),
            ('picking_id.state', 'not in', ('done', 'cancel')),
            ('state', 'not in', ('done', 'cancel')),
            ('move_dest_ids', '=', False),
        ]
        move_domain = self._append_factory_plan_category_domain(move_domain)
        moves = self.env['stock.move'].search(move_domain)
        if not moves:
            return []

        aggregated = {}
        for move in moves:
            key = move.product_id.id
            row = aggregated.setdefault(key, {
                'factory_plan_category': self._get_factory_plan_category_display(move.product_id),
                'product_name': move.product_id.display_name,
                'product_uom': self._get_move_uom_name(move),
                'total_demand': 0.0,
            })
            row['total_demand'] += move.product_uom_qty

        return sorted(
            aggregated.values(),
            key=lambda item: (item['factory_plan_category'], item['product_name']),
        )

    def _generate_xlsx_content(self):
        self.ensure_one()
        return self.with_context(lang=self._get_report_lang())._generate_xlsx_content_localized()

    def _generate_xlsx_content_localized(self):
        self.ensure_one()
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
        })
        text_style = workbook.add_format({'border': 1})
        number_style = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        datetime_style = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm:ss'})

        sheet1 = workbook.add_worksheet(self.env._('Details'))
        sheet1.right_to_left()
        sheet1.freeze_panes(1, 0)

        sheet1_headers = [
            self.env._('Reference'),
            self.env._('Product'),
            self.env._('Factory Plan Category'),
            self.env._('Created By'),
            self.env._('Creating Date'),
            self.env._('Demand'),
            self.env._('Unit of Measure'),
        ]
        for col, header in enumerate(sheet1_headers):
            sheet1.write(0, col, header, header_style)

        sheet1.set_column(0, 0, 22)
        sheet1.set_column(1, 1, 45)
        sheet1.set_column(2, 2, 25)
        sheet1.set_column(3, 3, 30)
        sheet1.set_column(4, 4, 22)
        sheet1.set_column(5, 5, 18)
        sheet1.set_column(6, 6, 16)

        row = 1
        sheet1_rows = self._get_sheet1_data()
        if not sheet1_rows:
            sheet1.write(row, 0, self.env._('No data for selected filters.'), text_style)
        else:
            for data in sheet1_rows:
                sheet1.write(row, 0, data['transfer_reference'], text_style)
                sheet1.write(row, 1, data['product_name'], text_style)
                sheet1.write(row, 2, data['factory_plan_category'], text_style)
                sheet1.write(row, 3, data['created_by'], text_style)
                if data['creating_date']:
                    sheet1.write_datetime(row, 4, data['creating_date'], datetime_style)
                else:
                    sheet1.write(row, 4, '', text_style)
                sheet1.write_number(row, 5, data['demand'], number_style)
                sheet1.write(row, 6, data['product_uom'], text_style)
                row += 1

        sheet2 = workbook.add_worksheet(self.env._('Summary'))
        sheet2.right_to_left()
        sheet2.freeze_panes(1, 0)

        sheet2_headers = [
            self.env._('Factory Plan Category'),
            self.env._('Product'),
            self.env._('Total Demand'),
            self.env._('Unit of Measure'),
        ]
        for col, header in enumerate(sheet2_headers):
            sheet2.write(0, col, header, header_style)

        sheet2.set_column(0, 0, 25)
        sheet2.set_column(1, 1, 45)
        sheet2.set_column(2, 2, 18)
        sheet2.set_column(3, 3, 16)

        row = 1
        sheet2_rows = self._get_sheet2_data()
        if not sheet2_rows:
            sheet2.write(row, 0, self.env._('No data for selected filters.'), text_style)
        else:
            for data in sheet2_rows:
                sheet2.write(row, 0, data['factory_plan_category'], text_style)
                sheet2.write(row, 1, data['product_name'], text_style)
                sheet2.write_number(row, 2, data['total_demand'], number_style)
                sheet2.write(row, 3, data['product_uom'], text_style)
                row += 1

        self._write_barcode_sheet(workbook, sheet1_rows)
        workbook.close()
        return output.getvalue()

    def _write_barcode_sheet(self, workbook, detail_rows):
        sheet = workbook.add_worksheet(self.env._('Barcodes'))
        sheet.freeze_panes(1, 0)

        header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
        })
        text_style = workbook.add_format({'border': 1, 'valign': 'vcenter'})

        for col, header in enumerate((self.env._('Created By'), self.env._('Barcode'))):
            sheet.write(0, col, header, header_style)
        sheet.set_column(0, 0, 30)

        seen = set()
        transfers = []
        for data in detail_rows:
            reference = data['transfer_reference']
            if not reference or reference in seen:
                continue
            seen.add(reference)
            transfers.append(data)
        transfers.sort(key=lambda data: data['transfer_reference'])

        if not transfers:
            sheet.set_column(1, 1, 40)
            sheet.write(1, 0, self.env._('No data for selected filters.'), text_style)
            return

        max_image_width = 0
        row = 1
        for data in transfers:
            reference = data['transfer_reference']
            sheet.write(row, 0, data['created_by'], text_style)
            sheet.write(row, 1, '', text_style)

            image = _code128_image(reference)
            if not image:
                sheet.write(row, 1, reference, text_style)
                row += 1
                continue

            stream, width, height = image
            sheet.set_row(row, (height + 8) * 72 / 96)
            sheet.insert_image(row, 1, 'barcode-%s.png' % row, {
                'image_data': stream,
                'x_offset': 4,
                'y_offset': 4,
            })
            max_image_width = max(max_image_width, width)
            row += 1

        sheet.set_column(1, 1, max((max_image_width + 12 - 5) / 7, 18))

    def action_print_excel(self):
        self.ensure_one()
        self.env['factory.plan.category.option'].sync_from_products()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/internal_transfer_excel_report/xlsx/{self.id}',
            'target': 'self',
        }
