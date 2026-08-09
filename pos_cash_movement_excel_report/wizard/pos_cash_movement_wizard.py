from collections import defaultdict
from datetime import datetime, time

from babel.dates import format_date as babel_format_date

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import babel_locale_parse, format_date, get_lang

TYPE_CASH_DELIVERY = 'تسليم نقد'
TYPE_PETTY_CASH_OUT = 'تعزيز السلفة النثرية'


class PosCashMovementWizard(models.TransientModel):
    _name = 'pos.cash.movement.wizard'
    _description = 'POS Cash Movement Excel Report Wizard'

    date_from = fields.Date(
        string='Session Opening Date From',
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(
        string='Session Opening Date To',
        required=True,
        default=fields.Date.context_today,
    )

    def _validate_filters(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Date From must be before or equal to Date To.'))

    def _get_session_domain(self):
        self.ensure_one()
        day_start = datetime.combine(self.date_from, time.min)
        day_end = datetime.combine(self.date_to, time.max)
        return [
            ('start_at', '>=', fields.Datetime.to_string(day_start)),
            ('start_at', '<=', fields.Datetime.to_string(day_end)),
        ]

    def _format_day_header(self, opening_date):
        """Day name header based on session opening date."""
        if not opening_date:
            return ''
        lang = get_lang(self.env)
        locale = babel_locale_parse(lang.code)
        day_name = babel_format_date(opening_date, format='EEEE', locale=locale)
        date_label = format_date(self.env, opening_date)
        return _('%(day)s — %(date)s', day=day_name, date=date_label)

    def _get_report_lines(self):
        """
        One row per transaction (no sums / no grouping of amounts).
        Filter sessions by start_at; transaction datetime is when the move was done.
        """
        self.ensure_one()
        self._validate_filters()

        sessions = self.env['pos.session'].search(
            self._get_session_domain(),
            order='start_at asc, id asc',
        )
        if not sessions:
            return []

        lines = []

        # تسليم نقد — both in-session and closing deliveries
        delivery_lines = self.env['pos.session.delivery.line'].search(
            [('session_id', 'in', sessions.ids)],
            order='id asc',
        )
        for delivery in delivery_lines:
            session = delivery.session_id
            if not session.start_at:
                continue
            opening_day = fields.Datetime.to_datetime(session.start_at).date()
            lines.append({
                'opening_day': opening_day,
                'pos_name': session.config_id.name or '',
                'transaction_datetime': delivery.create_date,
                'amount': delivery.amount or 0.0,
                'type': TYPE_CASH_DELIVERY,
                'sort_key': (
                    opening_day,
                    session.config_id.name or '',
                    fields.Datetime.to_datetime(delivery.create_date) if delivery.create_date else datetime.min,
                    delivery.id,
                ),
            })

        # تعزيز السلفة النثرية — Cash Out only (negative statement lines)
        for session in sessions:
            if not session.start_at:
                continue
            opening_day = fields.Datetime.to_datetime(session.start_at).date()
            for statement_line in session.statement_line_ids:
                amount = statement_line.amount or 0.0
                if amount >= 0:
                    continue
                lines.append({
                    'opening_day': opening_day,
                    'pos_name': session.config_id.name or '',
                    'transaction_datetime': statement_line.create_date,
                    'amount': abs(amount),
                    'type': TYPE_PETTY_CASH_OUT,
                    'sort_key': (
                        opening_day,
                        session.config_id.name or '',
                        fields.Datetime.to_datetime(statement_line.create_date)
                        if statement_line.create_date else datetime.min,
                        statement_line.id,
                    ),
                })

        lines.sort(key=lambda line: line['sort_key'])
        return lines

    def action_export_excel(self):
        self.ensure_one()
        self._validate_filters()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/pos_cash_movement_excel_report/xlsx/{self.id}',
            'target': 'self',
        }

    def _generate_xlsx_content(self):
        self.ensure_one()
        import io
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(_('Cash Movements'))

        day_header_style = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'bg_color': '#305496',
            'font_color': '#FFFFFF',
            'align': 'right',
            'valign': 'vcenter',
        })
        column_header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
        })
        text_style = workbook.add_format({'border': 1, 'align': 'right'})
        datetime_style = workbook.add_format({
            'border': 1,
            'num_format': 'yyyy-mm-dd hh:mm:ss',
            'align': 'center',
        })
        number_style = workbook.add_format({
            'border': 1,
            'num_format': '#,##0.00',
            'align': 'center',
        })

        headers = [
            _('POS Name'),
            _('Date & Time'),
            _('Amount'),
            _('Type'),
        ]
        sheet.set_column(0, 0, 32)
        sheet.set_column(1, 1, 22)
        sheet.set_column(2, 2, 14)
        sheet.set_column(3, 3, 28)

        report_lines = self._get_report_lines()
        row = 0

        if not report_lines:
            sheet.merge_range(
                row, 0, row, 3, self._format_day_header(self.date_from), day_header_style
            )
            sheet.set_row(row, 22)
            row += 1
            for col, header in enumerate(headers):
                sheet.write(row, col, header, column_header_style)
            row += 1
            sheet.write(row, 0, _('No data for selected filters.'), text_style)
            workbook.close()
            return output.getvalue()

        lines_by_day = defaultdict(list)
        for line in report_lines:
            lines_by_day[line['opening_day']].append(line)

        for opening_day in sorted(lines_by_day.keys()):
            day_label = self._format_day_header(opening_day)
            sheet.merge_range(row, 0, row, 3, day_label, day_header_style)
            sheet.set_row(row, 22)
            row += 1

            for col, header in enumerate(headers):
                sheet.write(row, col, header, column_header_style)
            row += 1

            for line in lines_by_day[opening_day]:
                sheet.write(row, 0, line['pos_name'], text_style)
                txn_dt = line['transaction_datetime']
                if txn_dt:
                    sheet.write_datetime(
                        row,
                        1,
                        fields.Datetime.to_datetime(txn_dt),
                        datetime_style,
                    )
                else:
                    sheet.write(row, 1, '', text_style)
                sheet.write_number(row, 2, line['amount'], number_style)
                sheet.write(row, 3, line['type'], text_style)
                row += 1

            # Blank separator between days (no totals)
            row += 1

        workbook.close()
        return output.getvalue()
