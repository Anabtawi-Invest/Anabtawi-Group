from odoo import _, fields, models


class PosDailyOperationsWizard(models.TransientModel):
    _name = 'pos.daily.operations.wizard'
    _description = 'Daily Operations Summary Report Wizard'

    business_date = fields.Date(string='Business Date', required=True, default=fields.Date.context_today)

    def _get_active_configs(self):
        return self.env['pos.config'].search([('active', '=', True)], order='name')

    def _get_report_rows(self):
        self.ensure_one()
        engine = self.env['pos.daily.ops.engine']
        configs = self._get_active_configs()
        figures = engine._compute_branch_figures(engine._get_period(self.business_date), configs)
        return [{'branch_name': config.name, **figures[config.id]} for config in configs]

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

        title_style = workbook.add_format({'bold': True, 'font_size': 14})
        label_style = workbook.add_format({'bold': True})
        header_style = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
        })
        text_style = workbook.add_format({'border': 1})
        total_text_style = workbook.add_format({'border': 1, 'bold': True})
        number_style = workbook.add_format({'border': 1, 'num_format': '#,##0.000'})
        total_number_style = workbook.add_format({'border': 1, 'bold': True, 'num_format': '#,##0.000'})
        date_style = workbook.add_format({'num_format': 'm/d/yyyy'})

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
        for col, header in enumerate(headers):
            sheet.write(header_row, col, header, header_style)

        sheet.set_column(0, 0, 28)
        for col in range(1, len(headers)):
            sheet.set_column(col, col, 14)

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

        workbook.close()
        return output.getvalue()
