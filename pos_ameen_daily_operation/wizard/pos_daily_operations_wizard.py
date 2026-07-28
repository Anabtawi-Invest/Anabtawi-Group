from collections import defaultdict
from datetime import datetime, time

from odoo import _, fields, models

PAYMENT_METHOD_TALABAT = 142
PAYMENT_METHOD_CAREEM = 143
PAYMENT_METHOD_MYTHINGS = 144
PAYMENT_METHOD_KABSEH = 145


class PosDailyOperationsWizard(models.TransientModel):
    _name = 'pos.daily.operations.wizard'
    _description = 'Daily Operations Summary Report Wizard'

    business_date = fields.Date(string='Business Date', required=True, default=fields.Date.context_today)

    def _get_day_bounds(self):
        self.ensure_one()
        day_start = datetime.combine(self.business_date, time.min)
        day_end = datetime.combine(self.business_date, time.max)
        return day_start, day_end

    def _get_active_configs(self):
        return self.env['pos.config'].search([('active', '=', True)], order='name')

    def _get_sessions_on_date(self):
        self.ensure_one()
        day_start, day_end = self._get_day_bounds()
        return self.env['pos.session'].search([
            ('start_at', '>=', fields.Datetime.to_string(day_start)),
            ('start_at', '<=', fields.Datetime.to_string(day_end)),
            ('config_id.active', '=', True),
        ], order='start_at asc')

    def _empty_branch_values(self):
        return {
            'sales': 0.0,
            'rahen_in': 0.0,
            'rahen_out': 0.0,
            'cash': 0.0,
            'visa': 0.0,
            'hospitality': 0.0,
            'talabat': 0.0,
            'careem': 0.0,
            'mythings': 0.0,
            'kabseh': 0.0,
            'delivery_amount': 0.0,
        }

    def _get_pledge_config_id(self, pledge):
        if pledge.pos_order_id:
            return pledge.pos_order_id.config_id.id
        if pledge.order_id:
            return pledge.order_id.pos_config_id.id
        return False

    def _pledge_order_on_date_domain(self, day_start, day_end):
        return [
            '|',
            '&', ('pos_order_id', '!=', False),
                 ('pos_order_id.date_order', '>=', fields.Datetime.to_string(day_start)),
                 ('pos_order_id.date_order', '<=', fields.Datetime.to_string(day_end)),
            '&', ('order_id', '!=', False),
                 ('order_id.create_date', '>=', fields.Datetime.to_string(day_start)),
                 ('order_id.create_date', '<=', fields.Datetime.to_string(day_end)),
        ]

    def _collect_pledge_totals(self, branch_data, active_config_ids):
        self.ensure_one()
        day_start, day_end = self._get_day_bounds()
        base_domain = self._pledge_order_on_date_domain(day_start, day_end)

        for state, field_name in (('active', 'rahen_in'), ('returned', 'rahen_out')):
            pledges = self.env['pos.advance.order.pledge'].search(
                base_domain + [('state', '=', state)]
            )
            for pledge in pledges:
                config_id = self._get_pledge_config_id(pledge)
                if not config_id or config_id not in active_config_ids:
                    continue
                branch_data[config_id][field_name] += pledge.pledge_subtotal or 0.0

    def _collect_payment_totals(self, branch_data, sessions):
        if not sessions:
            return

        grouped_payments = self.env['pos.payment']._read_group(
            [('session_id', 'in', sessions.ids)],
            ['session_id', 'payment_method_id'],
            ['amount:sum'],
        )
        for session, payment_method, total_amount in grouped_payments:
            config_id = session.config_id.id
            amount = total_amount or 0.0
            branch_data[config_id]['sales'] += amount
            if payment_method.daily_ops_report_type == 'cash':
                branch_data[config_id]['cash'] += amount
            elif payment_method.daily_ops_report_type == 'visa':
                branch_data[config_id]['visa'] += amount
            elif payment_method.daily_ops_report_type == 'hospitality':
                branch_data[config_id]['hospitality'] += amount
            if payment_method.id == PAYMENT_METHOD_TALABAT:
                branch_data[config_id]['talabat'] += amount
            elif payment_method.id == PAYMENT_METHOD_CAREEM:
                branch_data[config_id]['careem'] += amount
            elif payment_method.id == PAYMENT_METHOD_MYTHINGS:
                branch_data[config_id]['mythings'] += amount
            elif payment_method.id == PAYMENT_METHOD_KABSEH:
                branch_data[config_id]['kabseh'] += amount

    def _collect_session_delivery_amounts(self, branch_data, sessions_by_config):
        for config_id, config_sessions in sessions_by_config.items():
            if not config_sessions:
                continue
            branch_data[config_id]['delivery_amount'] = sum(
                session.delivery_amount or 0.0
                for session in config_sessions
            )

    def _get_report_rows(self):
        self.ensure_one()
        sessions = self._get_sessions_on_date()
        sessions_by_config = defaultdict(list)
        for session in sessions:
            sessions_by_config[session.config_id.id].append(session)

        configs = self._get_active_configs()
        active_config_ids = set(configs.ids)
        branch_data = defaultdict(self._empty_branch_values)

        self._collect_session_delivery_amounts(branch_data, sessions_by_config)
        self._collect_payment_totals(branch_data, sessions)
        self._collect_pledge_totals(branch_data, active_config_ids)

        rows = []
        for config in configs:
            values = branch_data[config.id]
            rows.append({
                'branch_name': config.name,
                **values,
            })
        return rows

    def _get_total_row(self, rows):
        numeric_fields = (
            'sales', 'rahen_in', 'rahen_out', 'cash', 'visa', 'hospitality',
            'talabat', 'careem', 'mythings', 'kabseh', 'delivery_amount',
        )
        totals = {field: sum(row[field] for row in rows) for field in numeric_fields}
        return {'branch_name': _('Total'), **totals}

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
        date_style = workbook.add_format({'num_format': 'm/d/yyyy', 'font_size': 9})

        sheet.write(0, 0, _('Daily Operations Summary'), title_style)
        sheet.write(2, 0, _('Business Date'), label_style)
        sheet.write(2, 1, self.business_date, date_style)

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
            _('Delivery Amount'),
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
            sheet.write_number(row_idx, 11, line['delivery_amount'], num_fmt)

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

        workbook.close()
        return output.getvalue()
