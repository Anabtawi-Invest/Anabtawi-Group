# -*- coding: utf-8 -*-
import base64
import datetime
import os
from io import BytesIO

import xlsxwriter

from odoo import fields, models


class PayrollReportWizard(models.TransientModel):
    _name = 'payroll.report.wizard'
    _description = 'Payroll and Withholding Tax Report Wizard (AR/3)'

    employee_id = fields.Many2one('hr.employee', string="Employee", required=True)
    year = fields.Selection(
        selection=[(str(y), str(y)) for y in range(2000, 2051)],
        string='Year',
        required=True,
        default=lambda self: str(fields.Date.today().year),
    )

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('l10n_jo_ar3_report.action_print_report').report_action(self)

    def _get_payslip_domain(self):
        self.ensure_one()
        return [
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '>=', f"{self.year}-01-01"),
            ('date_to', '<=', f"{self.year}-12-31"),
            ('state', 'in', ['validated', 'paid']),
        ]

    def _get_year_payslips(self):
        return self.env['hr.payslip'].search(self._get_payslip_domain())

    def _dedupe_contract_versions(self, versions):
        """Keep one version per (contract_date_start, contract_date_end), preserving order."""
        unique_ids = []
        seen = set()
        for version in versions:
            key = (version.contract_date_start, version.contract_date_end)
            if key not in seen:
                seen.add(key)
                unique_ids.append(version.id)
        return self.env['hr.version'].browse(unique_ids)

    def _get_contract_period_versions(self):
        """Unique contract periods from employee versions overlapping the selected year."""
        self.ensure_one()
        year = int(self.year)
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)
        versions = self.employee_id.version_ids.filtered(
            lambda v: v.contract_date_start
            and v.contract_date_start <= year_end
            and (not v.contract_date_end or v.contract_date_end >= year_start)
        ).sorted(key=lambda v: v.contract_date_start)
        return self._dedupe_contract_versions(versions)

    def _get_all_contract_versions(self):
        """All versions with a contract start date, for hire/termination display."""
        self.ensure_one()
        versions = self.employee_id.version_ids.filtered(
            lambda v: v.contract_date_start
        ).sorted(key=lambda v: v.contract_date_start)
        return self._dedupe_contract_versions(versions)

    def _get_worked_months(self, payslips=None):
        payslips = payslips if payslips is not None else self._get_year_payslips()
        months_set = set()
        for payslip in payslips:
            months_set.add(f"{payslip.date_from.year}-{payslip.date_from.month:02d}")
        return months_set

    def _get_salary_amounts(self, payslips=None):
        self.ensure_one()
        payslips = payslips if payslips is not None else self._get_year_payslips()
        company = self.env.company
        gross_rule_ids = set(company.gross_salary_rule_ids.ids)
        tax_rule_ids = set(company.income_tax_rule_ids.ids)

        gross_amount = 0.0
        tax_amount = 0.0
        for payslip in payslips:
            for line in payslip.line_ids:
                rule_id = line.salary_rule_id.id
                if rule_id in gross_rule_ids:
                    gross_amount += line.total
                if rule_id in tax_rule_ids:
                    tax_amount += line.total
        return gross_amount, tax_amount

    def _prepare_report_data(self):
        self.ensure_one()
        payslips = self._get_year_payslips()
        months_set = self._get_worked_months(payslips)
        gross_amount, tax_amount = self._get_salary_amounts(payslips)

        period_versions = self._get_contract_period_versions()
        all_versions = self._get_all_contract_versions()

        if period_versions:
            start_date = period_versions[0].contract_date_start
            if all(v.contract_date_end for v in period_versions):
                end_date = max(period_versions.mapped('contract_date_end'))
            else:
                end_date = ''
        elif all_versions:
            start_date = all_versions[0].contract_date_start
            end_date = all_versions[-1].contract_date_end or ''
        else:
            start_date = end_date = ''

        return {
            'employee_id': self.employee_id,
            'gross_amount': gross_amount,
            'tax_amount': tax_amount,
            'duration_str': f"{len(months_set)} ",
            'start_date': start_date,
            'end_date': end_date,
            'year': self.year,
            'months_set': months_set,
            'employer_name': (
                self.env.company.employer_display_name
                or self.employee_id.company_id.name
                or ''
            ),
        }

    def print_excel_report(self):
        self.ensure_one()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        worksheet = workbook.add_worksheet('PWTS Report')
        worksheet.hide_gridlines(2)
        worksheet.right_to_left()
        worksheet.set_paper(9)
        worksheet.set_portrait()
        worksheet.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        worksheet.fit_to_pages(1, 0)
        worksheet.center_horizontally()
        worksheet.set_print_scale(100)

        for col, width in enumerate([20, 20, 20, 20, 18, 18, 15, 20]):
            worksheet.set_column(col, col, width)

        header_format = workbook.add_format({
            'bold': True, 'align': 'center', 'border': 1,
            'font_size': 15, 'text_wrap': True, 'valign': 'vcenter',
        })
        cell_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1,
            'font_size': 13, 'text_wrap': True,
        })
        title_format = workbook.add_format({
            'bold': True, 'align': 'center', 'font_size': 14,
            'text_wrap': True, 'valign': 'vcenter',
        })
        title = workbook.add_format({
            'bold': True, 'align': 'center', 'font_size': 14,
            'text_wrap': True, 'valign': 'vcenter', 'border': 1,
        })
        sub_title_format = workbook.add_format({
            'bold': False, 'align': 'center', 'valign': 'vcenter',
            'font_size': 13, 'text_wrap': True, 'border': 0,
        })

        image_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '../static/description/2ChUlT.png'
        ))
        worksheet.insert_image('D1', image_path, {
            'x_scale': 0.2,
            'y_scale': 0.2,
            'x_offset': 50,
            'y_offset': 5,
        })
        worksheet.merge_range('A1:B1', 'وزارة المالية ', title_format)
        worksheet.merge_range('A2:B2', 'دائرة ضريبة الدخل والمبيعات ', title_format)
        worksheet.merge_range('A5:H5', 'شهادة مجموع الرواتب والاجور والضريبة المقتطعة', title_format)
        worksheet.merge_range(
            'A6:H6',
            '.صادر بالاستناد لأحكام الفقرة (و) من المادة (12) من قانون ضريبة الدخل رقم (34) لسنة 2014 وتعديلاته',
            sub_title_format,
        )
        worksheet.merge_range('A7:H8', 'معلومات الموظف\nاسم الموظف', title)
        worksheet.merge_range(
            'A31:H31',
            'اشهد ان المعلومات المدرجة اعلاه صحيحة وحقيقية وكاملة وغير منقوصة وأنني قمت بدفع ضريبتي الدخل والخدامات المقتطعتين والمبينتين اعلاه الى دائرة ضريبة الدخل والمبيعات  ',
            title_format,
        )

        employee = self.employee_id
        report_data = self._prepare_report_data()
        row = 8

        worksheet.merge_range(row, 0, row, 1, 'الاسم', header_format)
        worksheet.merge_range(row, 2, row, 3, 'الاب', header_format)
        worksheet.merge_range(row, 4, row, 5, 'الجد', header_format)
        worksheet.merge_range(row, 6, row, 7, 'العائلة', header_format)
        row += 1

        worksheet.merge_range(row, 0, row, 1, employee.legal_first_name or '', cell_format)
        worksheet.merge_range(row, 2, row, 3, employee.legal_father_name or '', cell_format)
        worksheet.merge_range(row, 4, row, 5, employee.legal_grandfather_name or '', cell_format)
        worksheet.merge_range(row, 6, row, 7, employee.legal_family_name or '', cell_format)
        row += 1

        worksheet.merge_range(row, 0, row, 1, 'الرقم الضريبي', header_format)
        worksheet.merge_range(row, 2, row, 3, 'الرقم الوطني / جواز سفر', header_format)
        worksheet.merge_range(row, 4, row, 5, 'صندوق بريد', header_format)
        worksheet.merge_range(row, 6, row, 7, 'الرمز البريدي', header_format)
        row += 1

        worksheet.merge_range(row, 0, row, 1, employee.tax_id or '', cell_format)
        worksheet.merge_range(
            row, 2, row, 3,
            employee.identification_id or employee.passport_id or '',
            cell_format,
        )
        worksheet.merge_range(row, 4, row, 5, '', cell_format)
        worksheet.merge_range(row, 6, row, 7, '', cell_format)
        row += 1

        worksheet.merge_range(row, 0, row, 3, 'العنوان', header_format)
        worksheet.merge_range(row, 4, row, 7, 'الهاتف', header_format)
        row += 1

        address = ''
        if employee.work_contact_id:
            address = employee.work_contact_id.contact_address or ''
        worksheet.merge_range(row, 0, row, 3, address, cell_format)
        worksheet.merge_range(row, 4, row, 7, employee.private_phone or '', cell_format)
        row += 1

        months_set = report_data['months_set']
        all_versions = self._get_all_contract_versions()
        start_contract_date = all_versions[0].contract_date_start if all_versions else ''
        end_contract_date = (
            all_versions[-1].contract_date_end
            if all_versions and all_versions[-1].contract_date_end
            else ''
        )

        worksheet.merge_range(row, 0, row, 1, 'الفترة الضريبية', header_format)
        worksheet.merge_range(row, 2, row, 3, 'مدة العمل اثناء الفترة الضريبية', header_format)
        worksheet.merge_range(row, 4, row, 5, 'تاريخ مباشرة العمل (التعيين)', header_format)
        worksheet.merge_range(row, 6, row, 7, 'تاريخ انتهاء العمل / انتهاء الخدمة', header_format)
        row += 1

        worksheet.merge_range(row, 0, row, 1, str(self.year), cell_format)
        worksheet.merge_range(row, 2, row, 3, len(months_set), cell_format)
        worksheet.merge_range(row, 4, row, 5, str(start_contract_date or ''), cell_format)
        worksheet.merge_range(row, 6, row, 7, str(end_contract_date or ''), cell_format)
        row += 3

        gross_amount = report_data['gross_amount']
        tax_amount = report_data['tax_amount']

        worksheet.merge_range(row, 0, row, 1, 'القيمة', header_format)
        worksheet.merge_range(row, 2, row + 1, 3, 'اجمالي الرواتب والاجور', header_format)
        worksheet.merge_range(row, 4, row, 5, 'القيمة', header_format)
        worksheet.merge_range(row, 6, row + 1, 7, 'الضريبة المقتطعة من إجمالي', header_format)
        row += 1

        worksheet.write(row, 0, 'فلس', header_format)
        worksheet.write(row, 1, 'دينار', header_format)
        worksheet.write(row, 4, 'فلس', header_format)
        worksheet.write(row, 5, 'دينار', header_format)
        row += 1

        entries = [
            'الرواتب والاجور',
            'الرواتب والاجور غير الشهرية',
            'مكافاة اعضاء مجلس الإدارة',
            'مكافاة نهاية الخدمة عن الخدمات ',
            'مكافاة نهاية الخدمة عن الخدمات ',
            'مكافاة نهاية الخدمة عن الخدمات',
        ]
        for idx, entry in enumerate(entries):
            worksheet.merge_range(row, 2, row, 3, entry, cell_format)
            worksheet.merge_range(row, 6, row, 7, entry, cell_format)
            if idx == 0:
                worksheet.write(row, 0, int((float(gross_amount) - int(gross_amount)) * 100), cell_format)
                worksheet.write(row, 1, int(gross_amount), cell_format)
                worksheet.write(row, 4, int((float(tax_amount) - int(tax_amount)) * 100), cell_format)
                worksheet.write(row, 5, int(tax_amount), cell_format)
            else:
                worksheet.write(row, 0, '', cell_format)
                worksheet.write(row, 1, '', cell_format)
                worksheet.write(row, 4, '', cell_format)
                worksheet.write(row, 5, '', cell_format)
            row += 1

        worksheet.merge_range(row, 2, row + 1, 3, 'اي مبالغ اخرى', cell_format)
        worksheet.write(row + 1, 0, '', cell_format)
        worksheet.write(row, 1, '', cell_format)
        worksheet.merge_range(row, 6, row, 7, 'اي مبالغ اخرى', cell_format)
        worksheet.write(row, 4, '', cell_format)
        worksheet.write(row, 5, '', cell_format)
        row += 1

        worksheet.merge_range(row, 6, row, 7, 'المساهمة الوطنية', cell_format)
        worksheet.write(row, 2, '', cell_format)
        worksheet.write(row, 3, '', cell_format)
        worksheet.write(row, 4, '', cell_format)
        worksheet.write(row, 5, '', cell_format)
        row += 1

        worksheet.merge_range(row, 2, row, 3, 'المجموع', header_format)
        worksheet.write(row, 0, '', cell_format)
        worksheet.write(row, 1, '', cell_format)
        worksheet.merge_range(row, 6, row, 7, 'المجموع', header_format)
        worksheet.write(row, 4, '', cell_format)
        worksheet.write(row, 5, '', cell_format)
        row += 4

        stamp_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bold': True, 'text_wrap': True, 'font_size': 12,
        })
        employer_name = report_data['employer_name']
        worksheet.merge_range(row, 0, row, 1, 'اسم صاحب العمل', stamp_format)
        worksheet.merge_range(row, 2, row, 4, employer_name, cell_format)
        worksheet.merge_range(row, 5, row + 1, 5, 'ختم وتوقيع صاحب الشركة', stamp_format)
        worksheet.merge_range(row, 6, row + 1, 7, '', stamp_format)
        row += 1

        worksheet.merge_range(row, 0, row, 1, 'الرقم الضريبي', stamp_format)
        worksheet.merge_range(row, 2, row, 4, self.env.company.vat or '', cell_format)
        row += 1

        worksheet.write(row, 0, ' :التاريخ ', cell_format)
        worksheet.write(row, 1, datetime.date.today().strftime('%Y-%m-%d'), cell_format)

        for row_num in range(100):
            worksheet.set_row(row_num, 30)

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': f"AR3 - {employee.name or 'No Name'} - {self.year}.xlsx",
            'type': 'binary',
            'datas': base64.b64encode(output.read()).decode('utf-8'),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
