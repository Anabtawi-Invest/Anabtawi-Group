from collections import defaultdict
from datetime import datetime, time

import pytz
from babel.dates import format_date as babel_format_date

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import babel_locale_parse, format_date, get_lang

TYPE_CASH_DELIVERY = 'تسليم نقد'
TYPE_PETTY_CASH_OUT = 'تعزيز السلفة النثرية'
DEFAULT_TZ = 'Asia/Amman'


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

    def _user_tz_name(self):
        """Prefer user timezone; default to Jordan time."""
        return self.env.user.tz or DEFAULT_TZ

    def _to_user_datetime(self, utc_dt):
        """Convert UTC datetime from DB to user/Jordan timezone (aware)."""
        if not utc_dt:
            return False
        utc_dt = fields.Datetime.to_datetime(utc_dt)
        return fields.Datetime.context_timestamp(self.with_context(tz=self._user_tz_name()), utc_dt)

    def _to_user_naive(self, utc_dt):
        """Local clock time without tzinfo (for Excel write_datetime)."""
        local_dt = self._to_user_datetime(utc_dt)
        if not local_dt:
            return False
        return local_dt.replace(tzinfo=None)

    def _local_day_bounds_as_utc(self, day_date):
        """Convert a local calendar day (Jordan/user TZ) to naive UTC bounds for ORM."""
        tz = pytz.timezone(self._user_tz_name())
        start_local = tz.localize(datetime.combine(day_date, time.min))
        end_local = tz.localize(datetime.combine(day_date, time.max))
        start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return start_utc, end_utc

    def _validate_filters(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Date From must be before or equal to Date To.'))

    def _get_session_domain(self):
        self.ensure_one()
        start_utc, _ = self._local_day_bounds_as_utc(self.date_from)
        _, end_utc = self._local_day_bounds_as_utc(self.date_to)
        return [
            ('start_at', '>=', fields.Datetime.to_string(start_utc)),
            ('start_at', '<=', fields.Datetime.to_string(end_utc)),
        ]

    def _format_day_header(self, opening_date):
        """Day name header based on session opening date (local calendar day)."""
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
        Datetimes are converted to user/Jordan timezone for display and day grouping.
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
            opening_local = self._to_user_datetime(session.start_at)
            opening_day = opening_local.date()
            txn_local = self._to_user_naive(delivery.create_date)
            lines.append({
                'opening_day': opening_day,
                'pos_name': session.config_id.name or '',
                'transaction_datetime': txn_local,
                'amount': delivery.amount or 0.0,
                'reason': (delivery.reason or '').strip(),
                'type': TYPE_CASH_DELIVERY,
                'sort_key': (
                    opening_day,
                    session.config_id.name or '',
                    txn_local or datetime.min,
                    delivery.id,
                ),
            })

        # تعزيز السلفة النثرية — Cash Out only (negative statement lines)
        for session in sessions:
            if not session.start_at:
                continue
            opening_local = self._to_user_datetime(session.start_at)
            opening_day = opening_local.date()
            for statement_line in session.statement_line_ids:
                amount = statement_line.amount or 0.0
                if amount >= 0:
                    continue
                txn_local = self._to_user_naive(statement_line.create_date)
                lines.append({
                    'opening_day': opening_day,
                    'pos_name': session.config_id.name or '',
                    'transaction_datetime': txn_local,
                    'amount': abs(amount),
                    'reason': (statement_line.payment_ref or '').strip(),
                    'type': TYPE_PETTY_CASH_OUT,
                    'sort_key': (
                        opening_day,
                        session.config_id.name or '',
                        txn_local or datetime.min,
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
            _('Reason'),
            _('Type'),
        ]
        sheet.set_column(0, 0, 32)
        sheet.set_column(1, 1, 22)
        sheet.set_column(2, 2, 14)
        sheet.set_column(3, 3, 40)
        sheet.set_column(4, 4, 28)

        report_lines = self._get_report_lines()
        row = 0
        last_col = 4

        if not report_lines:
            sheet.merge_range(
                row, 0, row, last_col, self._format_day_header(self.date_from), day_header_style
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
            sheet.merge_range(row, 0, row, last_col, day_label, day_header_style)
            sheet.set_row(row, 22)
            row += 1

            for col, header in enumerate(headers):
                sheet.write(row, col, header, column_header_style)
            row += 1

            for line in lines_by_day[opening_day]:
                sheet.write(row, 0, line['pos_name'], text_style)
                txn_dt = line['transaction_datetime']
                if txn_dt:
                    sheet.write_datetime(row, 1, txn_dt, datetime_style)
                else:
                    sheet.write(row, 1, '', text_style)
                sheet.write_number(row, 2, line['amount'], number_style)
                sheet.write(row, 3, line['reason'] or '', text_style)
                sheet.write(row, 4, line['type'], text_style)
                row += 1

            # Blank separator between days (no totals)
            row += 1

        workbook.close()
        return output.getvalue()
