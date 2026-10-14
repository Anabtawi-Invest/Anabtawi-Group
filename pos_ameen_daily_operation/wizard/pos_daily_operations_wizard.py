from collections import defaultdict
import logging

from babel.dates import format_date as babel_format_date

from odoo import _, fields, models
from odoo.tools.misc import babel_locale_parse, format_date, get_lang

_logger = logging.getLogger(__name__)

COLUMN_REPORT_TYPES = ('cash', 'visa', 'hospitality', 'talabat', 'careem', 'mythings', 'kabseh')


class PosDailyOperationsWizard(models.TransientModel):
    _name = 'pos.daily.operations.wizard'
    _description = 'Daily Operations Summary Report Wizard'

    business_date = fields.Date(string='Business Date', required=True, default=fields.Date.context_today)

    def _format_date_with_day_name(self, date_value):
        if not date_value:
            return ""
        lang = get_lang(self.env)
        locale = babel_locale_parse(lang.code)
        day_name = babel_format_date(date_value, format="EEEE", locale=locale)
        date_label = format_date(self.env, date_value)
        return _("%(date)s (%(day)s)", date=date_label, day=day_name)

    def _get_active_configs(self):
        return self.env['pos.config'].search([('active', '=', True)], order='name')

    def _get_period(self):
        self.ensure_one()
        return self.env['pos.daily.ops.engine']._get_period(self.business_date)

    def _get_report_rows(self):
        self.ensure_one()
        configs = self._get_active_configs()
        figures = self.env['pos.daily.ops.engine']._compute_branch_figures(self._get_period(), configs)
        return [{'branch_name': config.name, **figures[config.id]} for config in configs]

    def _get_total_row(self, rows):
        numeric_fields = (
            'sales', 'rahen_in', 'rahen_out', 'cash', 'visa', 'hospitality',
            'talabat', 'careem', 'mythings', 'kabseh', 'delivery_amount',
            'cash_out', 'delivery_cash', 'differences',
        )
        totals = {field: sum(row[field] for row in rows) for field in numeric_fields}
        return {'branch_name': _('Total'), **totals}

    def _get_report_type_label(self, payment_method):
        selection = dict(self.env['pos.payment.method']._fields['daily_ops_report_type']._description_selection(self.env))
        report_type = payment_method.daily_ops_report_type or 'none'
        return selection.get(report_type, report_type)

    def _get_report_columns_label(self, payment_method):
        if payment_method.daily_ops_report_type in COLUMN_REPORT_TYPES:
            return self._get_report_type_label(payment_method)
        return '-'

    def _get_sales_breakdown_lines(self, summary_rows):
        self.ensure_one()
        engine = self.env['pos.daily.ops.engine']
        configs = self._get_active_configs()
        sessions = engine._get_sessions(self._get_period(), configs)
        summary_by_branch = {row['branch_name']: row for row in summary_rows}

        aggregates = defaultdict(lambda: {'amount': 0.0, 'count': 0, 'payment_method': None})
        for payment in engine._get_payments(sessions):
            key = (payment.session_id.config_id.id, payment.payment_method_id.id)
            aggregates[key]['amount'] += payment.amount or 0.0
            aggregates[key]['count'] += 1
            aggregates[key]['payment_method'] = payment.payment_method_id

        lines = []
        for config in configs:
            branch_keys = sorted(
                (key for key in aggregates if key[0] == config.id),
                key=lambda key: aggregates[key]['payment_method'].name or '',
            )
            if not branch_keys:
                lines.append({
                    'row_type': 'detail',
                    'branch_name': config.name,
                    'payment_method': _('No payments'),
                    'report_type': '',
                    'report_columns': '',
                    'payment_count': 0,
                    'amount': 0.0,
                    'in_sales': False,
                })
            else:
                for key in branch_keys:
                    data = aggregates[key]
                    pm = data['payment_method']
                    lines.append({
                        'row_type': 'detail',
                        'branch_name': config.name,
                        'payment_method': pm.name,
                        'report_type': self._get_report_type_label(pm),
                        'report_columns': self._get_report_columns_label(pm),
                        'payment_count': data['count'],
                        'amount': data['amount'],
                        'in_sales': engine._is_in_sales(pm),
                    })

            in_sales_total = sum(
                aggregates[key]['amount']
                for key in branch_keys
                if engine._is_in_sales(aggregates[key]['payment_method'])
            )
            sheet_sales = summary_by_branch.get(config.name, {}).get('sales', 0.0)
            lines.append({
                'row_type': 'subtotal',
                'branch_name': config.name,
                'payment_method': _('Total (In Sales)'),
                'report_type': '',
                'report_columns': '',
                'payment_count': '',
                'amount': in_sales_total,
                'in_sales': True,
                'sheet_sales': sheet_sales,
                'difference': in_sales_total - sheet_sales,
            })

        return lines

    def _write_sales_breakdown_sheet(self, workbook, summary_rows, styles):
        sheet = workbook.add_worksheet(_('Sales Breakdown')[:31])
        header_style = styles['header']
        text_style = styles['text']
        number_style = styles['number']
        subtotal_text_style = styles['subtotal_text']
        subtotal_number_style = styles['subtotal_number']
        title_style = styles['title']
        label_style = styles['label']
        yes_style = styles.get('yes') or text_style
        no_style = styles.get('no') or text_style

        sheet.write(0, 0, _('Sales Breakdown by Payment Method'), title_style)
        sheet.write(2, 0, _('Business Date'), label_style)
        sheet.write(2, 1, self._format_date_with_day_name(self.business_date), text_style)
        sheet.write(3, 0, _('Note'), label_style)
        sheet.write(
            3, 1,
            _('Total (In Sales) must match the Sales column on the Daily Operations sheet. '
              'Hospitality payments are excluded from Sales.'),
            text_style,
        )

        headers = [
            _('Branch Name'),
            _('Payment Method'),
            _('Report Type'),
            _('Report Columns'),
            _('Payments Count'),
            _('Amount'),
            _('In Sales'),
            _('Sales (Sheet 1)'),
            _('Difference'),
        ]
        header_row = 5
        sheet.set_row(header_row, 28)
        for col, header in enumerate(headers):
            sheet.write(header_row, col, header, header_style)

        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 1, 22)
        sheet.set_column(2, 2, 12)
        sheet.set_column(3, 3, 16)
        sheet.set_column(4, 4, 10)
        sheet.set_column(5, 8, 12)

        breakdown_lines = self._get_sales_breakdown_lines(summary_rows)
        row_idx = header_row + 1
        if not breakdown_lines:
            sheet.write(row_idx, 0, _('No data for selected date.'), text_style)
            return

        for line in breakdown_lines:
            is_subtotal = line['row_type'] == 'subtotal'
            text_fmt = subtotal_text_style if is_subtotal else text_style
            num_fmt = subtotal_number_style if is_subtotal else number_style
            sheet.write(row_idx, 0, line['branch_name'], text_fmt)
            sheet.write(row_idx, 1, line['payment_method'], text_fmt)
            sheet.write(row_idx, 2, line['report_type'], text_fmt)
            sheet.write(row_idx, 3, line['report_columns'], text_fmt)
            if line['payment_count'] == '':
                sheet.write(row_idx, 4, '', text_fmt)
            else:
                sheet.write_number(row_idx, 4, line['payment_count'], num_fmt)
            sheet.write_number(row_idx, 5, line['amount'], num_fmt)
            in_sales_label = _('Yes') if line['in_sales'] else _('No')
            sheet.write(row_idx, 6, in_sales_label, yes_style if line['in_sales'] else no_style)
            if is_subtotal:
                sheet.write_number(row_idx, 7, line.get('sheet_sales', 0.0), num_fmt)
                sheet.write_number(row_idx, 8, line.get('difference', 0.0), num_fmt)
            else:
                sheet.write(row_idx, 7, '', text_fmt)
                sheet.write(row_idx, 8, '', text_fmt)
            row_idx += 1

        sheet.freeze_panes(header_row + 1, 0)
        sheet.autofilter(header_row, 0, max(row_idx - 1, header_row), len(headers) - 1)

    def _log_delivery_cash_and_differences_breakdown(self, rows, total_row):
        self.ensure_one()
        date_label = self._format_date_with_day_name(self.business_date)
        _logger.info(
            "Daily Operations Report — calculation breakdown | date=%s | wizard=%s",
            date_label,
            self.id,
        )
        if not rows:
            _logger.info("  No branch data for selected date.")
            return

        for row in rows:
            all_cash_in = (row['cash'] or 0.0) + (row['rahen_in'] or 0.0)
            _logger.info(
                "  Branch [%s]: Delivery Cash = cash_out(%s) + delivery_amount(%s) = %s",
                row['branch_name'],
                row['cash_out'],
                row['delivery_amount'],
                row['delivery_cash'],
            )
            _logger.info(
                "  Branch [%s]: Differences = cash(%s) + rahen_in(%s) - delivery_cash(%s) = %s",
                row['branch_name'],
                row['cash'],
                row['rahen_in'],
                row['delivery_cash'],
                row['differences'],
            )
            _logger.info(
                "  Branch [%s]: all_cash_in=%s (cash + rahen_in, used in Differences)",
                row['branch_name'],
                all_cash_in,
            )

        total_all_cash_in = (total_row['cash'] or 0.0) + (total_row['rahen_in'] or 0.0)
        _logger.info(
            "  TOTAL: Delivery Cash = cash_out(%s) + delivery_amount(%s) = %s",
            total_row['cash_out'],
            total_row['delivery_amount'],
            total_row['delivery_cash'],
        )
        _logger.info(
            "  TOTAL: Differences = cash(%s) + rahen_in(%s) - delivery_cash(%s) = %s",
            total_row['cash'],
            total_row['rahen_in'],
            total_row['delivery_cash'],
            total_row['differences'],
        )
        _logger.info(
            "  TOTAL: all_cash_in=%s (cash + rahen_in, used in Differences)",
            total_all_cash_in,
        )

    def action_export_excel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/pos_daily_operations_report/xlsx/{self.id}',
            'target': 'self',
        }

    def _generate_xlsx_content(self):
        self.ensure_one()
        import io
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        rows = self._get_report_rows()
        total_row = self._get_total_row(rows)
        self._log_delivery_cash_and_differences_breakdown(rows, total_row)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(_('Daily Operations'))

        title_style = workbook.add_format({'bold': True, 'font_size': 12})
        label_style = workbook.add_format({'bold': True, 'font_size': 9})
        header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'font_size': 9,
        })
        text_style = workbook.add_format({'border': 1, 'font_size': 9})
        total_text_style = workbook.add_format({'border': 1, 'bold': True, 'font_size': 9})
        number_style = workbook.add_format({'border': 1, 'num_format': '#,##0.000', 'font_size': 9})
        total_number_style = workbook.add_format({
            'border': 1, 'bold': True, 'num_format': '#,##0.000', 'font_size': 9,
        })

        sheet.write(0, 0, _('Daily Operations Summary'), title_style)
        sheet.write(2, 0, _('Business Date'), label_style)
        sheet.write(2, 1, self._format_date_with_day_name(self.business_date), text_style)

        headers = [
            _('Branch Name'),
            _('Sales'),
            _('Rahen In'),
            _('Rahen Out'),
            _('Cash'),
            _('Visa'),
            _('Hospitality'),
            _('Talabat'),
            _('Careem'),
            _('Mythings'),
            _('Kabseh'),
            _('Delivery Cash'),
            _('Differences'),
        ]
        header_row = 4
        sheet.set_row(header_row, 28)
        for col, header in enumerate(headers):
            sheet.write(header_row, col, header, header_style)

        sheet.set_column(0, 0, 14)
        for col in range(1, len(headers)):
            sheet.set_column(col, col, 9)

        def write_data_row(row_idx, line, is_total=False):
            text_fmt = total_text_style if is_total else text_style
            num_fmt = total_number_style if is_total else number_style
            sheet.write(row_idx, 0, line['branch_name'], text_fmt)
            sheet.write_number(row_idx, 1, line['sales'], num_fmt)
            sheet.write_number(row_idx, 2, line['rahen_in'], num_fmt)
            sheet.write_number(row_idx, 3, line['rahen_out'], num_fmt)
            sheet.write_number(row_idx, 4, line['cash'], num_fmt)
            sheet.write_number(row_idx, 5, line['visa'], num_fmt)
            sheet.write_number(row_idx, 6, line['hospitality'], num_fmt)
            sheet.write_number(row_idx, 7, line['talabat'], num_fmt)
            sheet.write_number(row_idx, 8, line['careem'], num_fmt)
            sheet.write_number(row_idx, 9, line['mythings'], num_fmt)
            sheet.write_number(row_idx, 10, line['kabseh'], num_fmt)
            sheet.write_number(row_idx, 11, line['delivery_cash'], num_fmt)
            sheet.write_number(row_idx, 12, line['differences'], num_fmt)

        row_idx = header_row + 1
        if not rows:
            sheet.write(row_idx, 0, _('No data for selected date.'), text_style)
        else:
            write_data_row(row_idx, total_row, is_total=True)
            row_idx += 1
            for line in rows:
                write_data_row(row_idx, line)
                row_idx += 1

        last_col = len(headers) - 1
        last_row = max(row_idx - 1, header_row)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.set_paper(9)
        sheet.set_margins(0.25, 0.25, 0.35, 0.35)
        sheet.center_horizontally()
        sheet.repeat_rows(header_row, header_row)
        sheet.print_area(0, 0, last_row, last_col)

        breakdown_styles = {
            'title': title_style,
            'label': label_style,
            'header': header_style,
            'text': text_style,
            'number': number_style,
            'subtotal_text': total_text_style,
            'subtotal_number': total_number_style,
        }
        self._write_sales_breakdown_sheet(workbook, rows, breakdown_styles)

        workbook.close()
        return output.getvalue()
