from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosPaymentSummaryWizard(models.TransientModel):
    _name = 'pos.payment.summary.wizard'
    _description = 'POS Payment Summary Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)
    pos_config_id = fields.Many2one('pos.config', string='Point of Sale')
    all_pos = fields.Boolean(string='All POS', default=False)
    group_by = fields.Selection(
        [
            ('session', 'By Session'),
            ('opening_day', 'By Opening Day'),
        ],
        string='Group By',
        required=True,
        default='session',
    )

    @api.onchange('all_pos')
    def _onchange_all_pos(self):
        if self.all_pos:
            self.pos_config_id = False

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            self.date_to = self.date_from

    @api.onchange('date_to')
    def _onchange_date_to(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            self.date_from = self.date_to

    def _validate_filters(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Date From must be before or equal to Date To.'))
        if not self.all_pos and not self.pos_config_id:
            raise UserError(_('Please select a Point of Sale or enable All POS.'))

    def _get_session_domain(self):
        self.ensure_one()
        date_start = datetime.combine(self.date_from, time.min)
        date_stop = datetime.combine(self.date_to, time.max)
        domain = [
            ('start_at', '>=', fields.Datetime.to_string(date_start)),
            ('start_at', '<=', fields.Datetime.to_string(date_stop)),
        ]
        if not self.all_pos:
            domain.append(('config_id', '=', self.pos_config_id.id))
        return domain

    def _get_report_lines(self):
        """Return report rows based on the selected grouping mode."""
        self.ensure_one()
        self._validate_filters()

        sessions = self.env['pos.session'].search(self._get_session_domain())
        if not sessions:
            return []

        grouped_payments = self.env['pos.payment']._read_group(
            [('session_id', 'in', sessions.ids)],
            ['session_id', 'payment_method_id'],
            ['amount:sum'],
        )

        if self.group_by == 'opening_day':
            return self._get_report_lines_by_opening_day(grouped_payments)
        return self._get_report_lines_by_session(grouped_payments)

    def _get_report_lines_by_session(self, grouped_payments):
        lines = []
        for session, payment_method, total_sales in grouped_payments:
            lines.append({
                'session_opening_date': session.start_at,
                'pos_name': session.config_id.name,
                'payment_method': payment_method.name,
                'total_sales': total_sales or 0.0,
                'currency': session.currency_id or self.env.company.currency_id,
            })

        lines.sort(key=lambda line: (
            line['session_opening_date'] or datetime.min,
            line['pos_name'],
            line['payment_method'],
        ))
        return lines

    def _get_report_lines_by_opening_day(self, grouped_payments):
        day_totals = {}
        for session, payment_method, total_sales in grouped_payments:
            if not session.start_at:
                continue
            opening_day = fields.Datetime.to_datetime(session.start_at).date()
            key = (opening_day, payment_method.id)
            if key not in day_totals:
                day_totals[key] = {
                    'opening_day': opening_day,
                    'payment_method': payment_method.name,
                    'total_sales': 0.0,
                }
            day_totals[key]['total_sales'] += total_sales or 0.0

        currency = self.env.company.currency_id
        lines = []
        for (_opening_day, _payment_method_id), line in sorted(
            day_totals.items(),
            key=lambda item: (item[0][0], item[1]['payment_method']),
        ):
            line['currency'] = currency
            lines.append(line)
        return lines

    def _get_report_data(self):
        self.ensure_one()
        return {
            'wizard_id': self.id,
            'date_from': fields.Date.to_string(self.date_from),
            'date_to': fields.Date.to_string(self.date_to),
            'all_pos': self.all_pos,
            'group_by': self.group_by,
            'pos_config_name': self.pos_config_id.name if self.pos_config_id else _('All POS'),
        }

    def action_print_pdf(self):
        self.ensure_one()
        data = self._get_report_data()
        return self.env.ref(
            'pos_payment_summary_report.action_report_pos_payment_summary'
        ).report_action(self, data=data)

    def action_export_excel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/pos_payment_summary_report/xlsx/{self.id}',
            'target': 'self',
        }

    def _generate_xlsx_content(self):
        self.ensure_one()
        import io
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(_('Payment Summary'))
        sheet.freeze_panes(1, 0)

        header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
        })
        text_style = workbook.add_format({'border': 1})
        datetime_style = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm'})
        date_style = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})
        number_style = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})

        if self.group_by == 'opening_day':
            headers = [_('Opening Day'), _('Payment Method'), _('Total Sales')]
        else:
            headers = [
                _('Session Opening Date'),
                _('POS Name'),
                _('Payment Method'),
                _('Total Sales'),
            ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_style)

        if self.group_by == 'opening_day':
            sheet.set_column(0, 0, 16)
            sheet.set_column(1, 1, 25)
            sheet.set_column(2, 2, 18)
        else:
            sheet.set_column(0, 0, 22)
            sheet.set_column(1, 1, 30)
            sheet.set_column(2, 2, 25)
            sheet.set_column(3, 3, 18)

        row = 1
        lines = self._get_report_lines()
        if not lines:
            sheet.write(row, 0, _('No data for selected filters.'), text_style)
        elif self.group_by == 'opening_day':
            for line in lines:
                opening_day = line['opening_day']
                if opening_day:
                    sheet.write_datetime(
                        row, 0, datetime.combine(opening_day, time.min), date_style
                    )
                else:
                    sheet.write(row, 0, '', text_style)
                sheet.write(row, 1, line['payment_method'], text_style)
                sheet.write_number(row, 2, line['total_sales'], number_style)
                row += 1
        else:
            for line in lines:
                opening_date = line['session_opening_date']
                if opening_date:
                    sheet.write_datetime(row, 0, fields.Datetime.to_datetime(opening_date), datetime_style)
                else:
                    sheet.write(row, 0, '', text_style)
                sheet.write(row, 1, line['pos_name'], text_style)
                sheet.write(row, 2, line['payment_method'], text_style)
                sheet.write_number(row, 3, line['total_sales'], number_style)
                row += 1

        workbook.close()
        return output.getvalue()
