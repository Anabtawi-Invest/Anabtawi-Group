from datetime import datetime, time, timedelta
import io

from odoo import _, fields, models
from odoo.exceptions import UserError

class InternalTransferReportWizard(models.TransientModel):
    _name = 'internal.transfer.report.wizard'
    _description = 'Internal Transfer Report Wizard'

    filter_type = fields.Selection([
        ('week', 'This Week'),
        ('last_month', 'Last Month'),
        ('custom', 'Custom'),
    ], default='week', required=True)

    date_from = fields.Date()
    date_to = fields.Date()

    category_id = fields.Many2one(
        'product.category',
        string='Product Category'
    )

    def _compute_dates(self):
        today = fields.Date.today()

        if self.filter_type == 'week':
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)

        elif self.filter_type == 'last_month':
            first_day = today.replace(day=1)
            last_month_end = first_day - timedelta(days=1)
            start = last_month_end.replace(day=1)
            end = last_month_end

        else:
            if not self.date_from or not self.date_to:
                raise UserError(_("Please set both start and end dates for custom filter."))
            start = self.date_from
            end = self.date_to

        return start, end

    def _get_report_groups(self):
        self.ensure_one()

        date_from, date_to = self._compute_dates()
        date_from_dt = fields.Datetime.to_string(datetime.combine(date_from, time.min))
        date_to_dt = fields.Datetime.to_string(datetime.combine(date_to, time.max))
        picking_domain = [
            ('picking_type_code', '=', 'internal'),
            ('scheduled_date', '>=', date_from_dt),
            ('scheduled_date', '<=', date_to_dt),
            ('state', '!=', 'cancel'),
        ]
        picking_ids = self.env['stock.picking'].search(picking_domain).ids
        if not picking_ids:
            return []

        move_domain = [
            ('picking_id.picking_type_code', '=', 'internal'),
            ('picking_id', 'in', picking_ids),
            ('state', '!=', 'cancel'),
        ]
        if self.category_id:
            move_domain.append(('product_id.categ_id', 'child_of', self.category_id.id))

        moves = self.env['stock.move'].search(move_domain, order='product_id, picking_id')
        result = {}
        for move in moves:
            product = move.product_id
            planned_qty = move.product_uom_qty
            actual_qty = move.quantity
            delivered_qty = move.quantity if move.state == 'done' else 0.0
            group = result.setdefault(product.id, {
                'product_name': product.display_name,
                'uom_name': move.product_uom.display_name or product.uom_id.display_name,
                'rows': {},
                'total_qty': 0.0,
                'total_actual_qty': 0.0,
                'total_delivered_qty': 0.0,
            })

            branch_name = (
                move.picking_id.partner_id.display_name
                or move.picking_id.location_dest_id.display_name
                or _('Undefined')
            )
            row_data = group['rows'].setdefault(branch_name, {
                'branch_contact': branch_name,
                'product_name': product.display_name,
                'quantity': 0.0,
                'actual_quantity': 0.0,
                'delivered_quantity': 0.0,
            })

            row_data['quantity'] += planned_qty
            row_data['actual_quantity'] += actual_qty
            row_data['delivered_quantity'] += delivered_qty

            group['total_qty'] += planned_qty
            group['total_actual_qty'] += actual_qty
            group['total_delivered_qty'] += delivered_qty

        grouped_data = []
        for group in sorted(result.values(), key=lambda item: item['product_name']):
            group['rows'] = [group['rows'][key] for key in sorted(group['rows'])]
            grouped_data.append(group)
        return grouped_data

    def _generate_xlsx_content(self):
        self.ensure_one()
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Internal Transfers')
        sheet.right_to_left()
        sheet.freeze_panes(1, 0)

        header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
        })
        text_style = workbook.add_format({'border': 1})
        number_style = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        group_text_style = workbook.add_format({'bold': True, 'bg_color': '#E9ECEF', 'border': 1})
        group_number_style = workbook.add_format({
            'bold': True,
            'bg_color': '#E9ECEF',
            'border': 1,
            'num_format': '#,##0.00',
        })

        headers = [
            _('Branch Contact'),
            _('Products'),
            _('Quantity'),
            _('Actual Quantity'),
            _('Delivered Quantity'),
            _('Unit of Measure'),
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_style)

        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 1, 45)
        sheet.set_column(2, 4, 18)
        sheet.set_column(5, 5, 16)

        row = 1
        groups = self._get_report_groups()
        if not groups:
            sheet.write(row, 0, _('No data for selected filters.'), text_style)
        else:
            for group in groups:
                sheet.write(row, 0, _('Total'), group_text_style)
                sheet.write(row, 1, group['product_name'], group_text_style)
                sheet.write_number(row, 2, group['total_qty'], group_number_style)
                sheet.write_number(row, 3, group['total_actual_qty'], group_number_style)
                sheet.write_number(row, 4, group['total_delivered_qty'], group_number_style)
                sheet.write(row, 5, group['uom_name'], group_text_style)
                row += 1

                for detail in group['rows']:
                    sheet.write(row, 0, detail['branch_contact'], text_style)
                    sheet.write(row, 1, detail['product_name'], text_style)
                    sheet.write_number(row, 2, detail['quantity'], number_style)
                    sheet.write_number(row, 3, detail['actual_quantity'], number_style)
                    sheet.write_number(row, 4, detail['delivered_quantity'], number_style)
                    sheet.write(row, 5, group['uom_name'], text_style)
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