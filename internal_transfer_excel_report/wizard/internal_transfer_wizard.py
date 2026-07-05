from datetime import datetime, time, timedelta
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
        string='Factory Plan Categories',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        self.env['factory.plan.category.option'].sync_from_products()
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

    def _get_picking_state_labels(self):
        return dict(
            self.env['stock.picking'].fields_get(['state'])['state']['selection']
        )

    def _append_factory_plan_category_domain(self, move_domain):
        self.ensure_one()
        if self.all_factory_plan_categories:
            return move_domain

        if not self.factory_plan_category_ids:
            return move_domain

        named_categories = self.factory_plan_category_ids.filtered(
            lambda option: not option.is_uncategorized
        )
        include_uncategorized = bool(
            self.factory_plan_category_ids.filtered('is_uncategorized')
        )

        if named_categories and include_uncategorized:
            move_domain.extend([
                '|',
                ('product_id.product_tmpl_id.factory_plan_category', 'in', named_categories.mapped('name')),
                '|',
                ('product_id.product_tmpl_id.factory_plan_category', '=', False),
                ('product_id.product_tmpl_id.factory_plan_category', '=', ''),
            ])
        elif named_categories:
            move_domain.append(
                ('product_id.product_tmpl_id.factory_plan_category', 'in', named_categories.mapped('name'))
            )
        elif include_uncategorized:
            move_domain.extend([
                '|',
                ('product_id.product_tmpl_id.factory_plan_category', '=', False),
                ('product_id.product_tmpl_id.factory_plan_category', '=', ''),
            ])

        return move_domain

    def _get_base_picking_domain(self):
        date_from_dt, date_to_dt = self._compute_dates()
        return [
            ('picking_type_code', '=', 'internal'),
            ('scheduled_date', '>=', date_from_dt),
            ('scheduled_date', '<=', date_to_dt),
        ]

    def _get_sheet1_data(self):
        self.ensure_one()

        picking_domain = self._get_base_picking_domain()
        picking_domain.append(('state', '!=', 'cancel'))
        picking_ids = self.env['stock.picking'].search(picking_domain).ids
        if not picking_ids:
            return []

        move_domain = [
            ('picking_id.picking_type_code', '=', 'internal'),
            ('picking_id', 'in', picking_ids),
            ('state', '!=', 'cancel'),
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
                'product_name': move.product_id.display_name,
                'factory_plan_category': self._get_factory_plan_category_display(move.product_id),
                'created_by': picking.create_uid.display_name or self.env._('Undefined'),
                'creating_date': picking.create_date,
                'demand': move.product_uom_qty,
                'quantity': move.quantity,
            })
        return rows

    def _get_sheet2_data(self):
        self.ensure_one()

        picking_domain = self._get_base_picking_domain()
        picking_domain.append(('state', 'in', ('done', 'cancel')))
        picking_ids = self.env['stock.picking'].search(picking_domain).ids
        if not picking_ids:
            return []

        move_domain = [
            ('picking_id.picking_type_code', '=', 'internal'),
            ('picking_id', 'in', picking_ids),
            ('picking_id.state', 'in', ('done', 'cancel')),
            ('move_dest_ids', '=', False),
        ]
        move_domain = self._append_factory_plan_category_domain(move_domain)

        moves = self.env['stock.move'].search(move_domain)
        aggregated = {}
        state_labels = self._get_picking_state_labels()

        for move in moves:
            picking = move.picking_id
            key = (
                self._get_factory_plan_category_display(move.product_id),
                move.product_id.display_name,
                picking.state,
            )
            row = aggregated.setdefault(key, {
                'factory_plan_category': key[0],
                'product_name': key[1],
                'status': state_labels.get(picking.state, picking.state),
                'total_demand': 0.0,
            })
            row['total_demand'] += move.product_uom_qty

        return sorted(
            aggregated.values(),
            key=lambda item: (item['factory_plan_category'], item['product_name'], item['status']),
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
            self.env._('Product'),
            self.env._('Factory Plan Category'),
            self.env._('Created By'),
            self.env._('Creating Date'),
            self.env._('Demand'),
            self.env._('Quantity'),
        ]
        for col, header in enumerate(sheet1_headers):
            sheet1.write(0, col, header, header_style)

        sheet1.set_column(0, 0, 45)
        sheet1.set_column(1, 1, 25)
        sheet1.set_column(2, 2, 30)
        sheet1.set_column(3, 3, 22)
        sheet1.set_column(4, 5, 18)

        row = 1
        sheet1_rows = self._get_sheet1_data()
        if not sheet1_rows:
            sheet1.write(row, 0, self.env._('No data for selected filters.'), text_style)
        else:
            for data in sheet1_rows:
                sheet1.write(row, 0, data['product_name'], text_style)
                sheet1.write(row, 1, data['factory_plan_category'], text_style)
                sheet1.write(row, 2, data['created_by'], text_style)
                if data['creating_date']:
                    sheet1.write_datetime(row, 3, data['creating_date'], datetime_style)
                else:
                    sheet1.write(row, 3, '', text_style)
                sheet1.write_number(row, 4, data['demand'], number_style)
                sheet1.write_number(row, 5, data['quantity'], number_style)
                row += 1

        sheet2 = workbook.add_worksheet(self.env._('Summary'))
        sheet2.right_to_left()
        sheet2.freeze_panes(1, 0)

        sheet2_headers = [
            self.env._('Factory Plan Category'),
            self.env._('Product'),
            self.env._('Total Demand'),
            self.env._('Status'),
        ]
        for col, header in enumerate(sheet2_headers):
            sheet2.write(0, col, header, header_style)

        sheet2.set_column(0, 0, 25)
        sheet2.set_column(1, 1, 45)
        sheet2.set_column(2, 2, 18)
        sheet2.set_column(3, 3, 18)

        row = 1
        sheet2_rows = self._get_sheet2_data()
        if not sheet2_rows:
            sheet2.write(row, 0, self.env._('No data for selected filters.'), text_style)
        else:
            for data in sheet2_rows:
                sheet2.write(row, 0, data['factory_plan_category'], text_style)
                sheet2.write(row, 1, data['product_name'], text_style)
                sheet2.write_number(row, 2, data['total_demand'], number_style)
                sheet2.write(row, 3, data['status'], text_style)
                row += 1

        workbook.close()
        return output.getvalue()

    def action_print_excel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/internal_transfer_excel_report/xlsx/{self.id}',
            'target': 'self',
        }
