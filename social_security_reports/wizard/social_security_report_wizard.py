# -*- coding: utf-8 -*-
import io
import base64
import calendar
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class SocialSecurityReportWizard(models.TransientModel):
    _name = 'social_security_report.wizard'
    _description = 'Social Security Reports Wizard'

    def _get_year_selection(self):
        current_year = fields.Date.context_today(self).year
        return [(str(y), str(y)) for y in range(current_year - 5, current_year + 6)]

    report_type = fields.Selection([
        ('add_new', 'Add New Employees to Social Security'),
        ('terminate', 'Terminate Employees from Social Security'),
    ], string="Report Type", default='add_new', required=True)

    month = fields.Selection([
        ('1', '01 - January'),
        ('2', '02 - February'),
        ('3', '03 - March'),
        ('4', '04 - April'),
        ('5', '05 - May'),
        ('6', '06 - June'),
        ('7', '07 - July'),
        ('8', '08 - August'),
        ('9', '09 - September'),
        ('10', '10 - October'),
        ('11', '11 - November'),
        ('12', '12 - December'),
    ], string="Month", required=True, default=lambda self: str(fields.Date.context_today(self).month))

    year = fields.Selection(
        selection=_get_year_selection,
        string="Year",
        required=True,
        default=lambda self: str(fields.Date.context_today(self).year)
    )

    report_date = fields.Date(
        string="Report Date",
        default=fields.Date.context_today,
        required=True
    )

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        required=False
    )

    excel_file = fields.Binary(string="Excel File", readonly=True)
    excel_filename = fields.Char(string="Excel Filename", readonly=True)
    state = fields.Selection([
        ('choose', 'Choose Parameters'),
        ('get', 'Download File')
    ], default='choose')

    def get_print_footer_info(self):
        """
        Returns (user_code, user_name, timestamp_str) for report footer
        """
        self.ensure_one()
        user = self.env.user
        user_code = '007100'
        if 'employee_id' in user._fields and user.employee_id:
            emp = user.employee_id
            for attr in ['employee_number', 'barcode', 'identification_id']:
                if attr in emp._fields and emp[attr]:
                    user_code = str(emp[attr]).strip()
                    break
        user_name = user.name.upper() if user.name else 'ADMIN'
        now_str = fields.Datetime.context_timestamp(self, datetime.now()).strftime('%d/%m/%Y %H:%M:%S')
        return user_code, user_name, now_str

    def get_month_name_ar(self):
        month_names = {
            1: 'كانون الثاني',
            2: 'شباط',
            3: 'آذار',
            4: 'نيسان',
            5: 'أيار',
            6: 'حزيران',
            7: 'تموز',
            8: 'آب',
            9: 'أيلول',
            10: 'تشرين الأول',
            11: 'تشرين الثاني',
            12: 'كانون الأول',
        }
        return month_names.get(int(self.month), '')

    def get_date_range(self):
        m = int(self.month)
        y = int(self.year)
        _, last_day = calendar.monthrange(y, m)
        start_date = date(y, m, 1)
        end_date = date(y, m, last_day)

        # Previous month
        if m == 1:
            prev_m = 12
            prev_y = y - 1
        else:
            prev_m = m - 1
            prev_y = y
        _, prev_last_day = calendar.monthrange(prev_y, prev_m)
        prev_start_date = date(prev_y, prev_m, 1)
        prev_end_date = date(prev_y, prev_m, prev_last_day)

        return start_date, end_date, prev_start_date, prev_end_date

    def get_new_employees_data(self):
        """
        Add New Employees TO Social Security logic:
        1. Current Month M:
           - Started in Month M (start_date_M <= sd <= end_date_M)
           - AND (sd.day <= 16 OR (report_date - sd).days >= 16 OR (end_date_M - sd).days + 1 >= 16)
        2. Previous Month M-1:
           - Started in Month M-1 after the 16th (sd.day > 16)
           - AND completed >= 16 days by report_date (or end of Month M)
        Excludes employees with exempt_from_social_security == True.
        """
        self.ensure_one()
        start_date, end_date, prev_start, prev_end = self.get_date_range()
        rep_date = self.report_date or end_date

        domain = [('active', 'in', [True, False])]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        employees = self.env['hr.employee'].search(domain)

        matched_employees = []
        for emp in employees:
            if emp.is_exempt_from_ssc():
                continue

            sd = emp.get_ssc_start_date()
            if not sd:
                continue

            included = False
            # Check Case 1: Started in current month
            if start_date <= sd <= end_date:
                days_worked = (end_date - sd).days + 1
                days_since_start = (rep_date - sd).days if rep_date >= sd else 0
                if sd.day <= 16 or days_worked >= 16 or days_since_start >= 16:
                    included = True
            # Check Case 2: Started in previous month after the 16th
            elif prev_start <= sd <= prev_end:
                if sd.day > 16:
                    days_total = (end_date - sd).days + 1
                    if days_total >= 16:
                        included = True

            if not included:
                continue

            # Check payslip for the selected month (start_date to end_date):
            # If the employee already has social security deduction in that month's payslip -> exclude him.
            # If they do not have social security deduction (or have no payslip) -> include him.
            if hasattr(emp, 'has_ssc_deduction_in_period') and emp.has_ssc_deduction_in_period(start_date, end_date):
                continue

            matched_employees.append(emp)

        # Sort by start date, then employee_number
        matched_employees.sort(key=lambda e: (e.get_ssc_start_date() or date.min, e.employee_number or ''))
        return matched_employees

    def get_terminated_employees_data(self):
        """
        Terminate Employees from Social Security logic:
        Employees whose termination date (or contract end date) falls within selected Month M and Year Y.
        Priority for termination date:
        1. departure_date (Termination Date)
        2. profile_termination_date
        3. termination_date
        4. profile_contract_end_date
        5. contract_date_end
        6. date_end
        Excludes employees with exempt_from_social_security == True.
        """
        self.ensure_one()
        start_date, end_date, _, _ = self.get_date_range()

        domain = [('active', 'in', [True, False])]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        employees = self.env['hr.employee'].search(domain)

        matched_employees = []
        for emp in employees:
            if emp.is_exempt_from_ssc():
                continue

            ed = emp.get_ssc_end_date()
            if not ed:
                continue

            if start_date <= ed <= end_date:
                # Check payslip for the selected month (start_date to end_date):
                # If the employee already has social security deduction in that month's payslip -> exclude him.
                # If they do not have social security deduction (or have no payslip) -> include him.
                if hasattr(emp, 'has_ssc_deduction_in_period') and emp.has_ssc_deduction_in_period(start_date, end_date):
                    continue

                matched_employees.append(emp)

        # Sort by termination date, then employee_number
        matched_employees.sort(key=lambda e: (e.get_ssc_end_date() or date.min, e.employee_number or ''))
        return matched_employees

    def action_print_pdf(self):
        self.ensure_one()
        if self.report_type == 'add_new':
            return self.env.ref('social_security_reports.action_report_social_security_new').report_action(self)
        else:
            return self.env.ref('social_security_reports.action_report_social_security_terminated').report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("XlsxWriter is required to export Excel reports."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Page 1')
        worksheet.right_to_left()

        if self.report_type == 'add_new':
            self._generate_add_new_excel(workbook, worksheet)
            filename = f"Social Security Members List {int(self.month):02d}_{self.year}.xlsx"
        else:
            self._generate_terminate_excel(workbook, worksheet)
            filename = f"Terminated Social Security List {int(self.month):02d}_{self.year}.xlsx"

        workbook.close()
        output.seek(0)
        self.excel_file = base64.b64encode(output.read())
        self.excel_filename = filename
        self.state = 'get'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'social_security_report.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _generate_add_new_excel(self, workbook, worksheet):
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D9D9D9',
            'border': 1,
            'font_name': 'Arial',
            'font_size': 10,
        })
        text_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Arial',
            'font_size': 10,
        })
        num_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Arial',
            'font_size': 10,
            'num_format': '#,##0',
        })

        headers = [
            'رمز المهنة الخطرة',
            'الأجر الشهري',
            'الرقم الوظيفي',
            'تاريخ الميلاد السنة',
            'تاريخ الميلاد الشهر',
            'تاريخ الميلاد اليوم',
            'الرقم الشخصي',
            'تاريخ البدء',
            'رقم تأمين المؤمن عليه',
            'الرقم الوطني للمؤمن عليه الأردني'
        ]

        worksheet.set_row(0, 24)
        for col_idx, header in enumerate(headers):
            worksheet.write(0, col_idx, header, header_format)

        col_widths = [16, 14, 14, 18, 18, 18, 18, 16, 22, 28]
        for c, w in enumerate(col_widths):
            worksheet.set_column(c, c, w)

        employees = self.get_new_employees_data()
        row = 1
        for emp in employees:
            worksheet.set_row(row, 20)
            wage = emp.get_ssc_wage()
            emp_num = emp.get_formatted_employee_number()

            bdate = emp.birthday
            byear = str(bdate.year) if bdate else ''
            bmonth = str(bdate.month) if bdate else ''
            bday = str(bdate.day) if bdate else ''

            nat_id = emp.get_national_id()
            ssn = emp.get_ssc_number()
            personal_num = emp.get_personal_id()

            sdate = emp.get_ssc_start_date()
            start_str = sdate.strftime('%d/%m/%Y') if sdate else ''

            worksheet.write(row, 0, '', text_center)
            worksheet.write(row, 1, int(wage) if wage else '', num_center)
            worksheet.write(row, 2, emp_num, text_center)
            worksheet.write(row, 3, byear, text_center)
            worksheet.write(row, 4, bmonth, text_center)
            worksheet.write(row, 5, bday, text_center)
            worksheet.write(row, 6, personal_num, text_center)
            worksheet.write(row, 7, start_str, text_center)
            worksheet.write(row, 8, ssn, text_center)
            worksheet.write(row, 9, nat_id, text_center)

            row += 1

    def _generate_terminate_excel(self, workbook, worksheet):
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D9D9D9',
            'border': 1,
            'font_name': 'Arial',
            'font_size': 10,
        })
        text_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Arial',
            'font_size': 10,
        })
        num_center = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Arial',
            'font_size': 10,
            'num_format': '#,##0',
        })

        worksheet.set_row(0, 28)
        worksheet.write(0, 0, 'الفرع أو\nالمديرية', header_format)
        worksheet.write(0, 1, 'سبب\nالإيقاف', header_format)
        worksheet.merge_range(0, 2, 0, 4, 'تاريخ إيقاف\nالاقتطاع', header_format)
        worksheet.merge_range(0, 5, 0, 6, 'الأجر الشهري\nالخاضع للاقتطاع', header_format)
        worksheet.merge_range(0, 7, 0, 10, 'اسم المؤمن عليه', header_format)
        worksheet.write(0, 11, 'رقم التأمين الثابت', header_format)
        worksheet.write(0, 12, 'الرقم المتسلسل', header_format)

        col_widths = [14, 14, 8, 6, 6, 8, 6, 14, 12, 12, 12, 16, 12]
        for c, w in enumerate(col_widths):
            worksheet.set_column(c, c, w)

        employees = self.get_terminated_employees_data()
        row = 1
        seq = 1
        for emp in employees:
            worksheet.set_row(row, 20)
            wage = emp.get_ssc_wage()
            dinars = int(wage)
            fils = int(round((wage - dinars) * 1000))
            fils_str = f"{fils:03d}"

            ed = emp.get_ssc_end_date()
            eyear = f"{ed.year:04d}" if ed else ''
            emonth = f"{ed.month:02d}" if ed else ''
            eday = f"{ed.day:02d}" if ed else ''

            first, father, grandfather, family = emp.get_arabic_name_parts()
            ssn = emp.get_ssc_number()

            reason = ''
            if 'departure_reason_id' in emp._fields and emp.departure_reason_id:
                reason = emp.departure_reason_id.name or ''
            elif 'profile_employment_status' in emp._fields and emp.profile_employment_status:
                reason = emp.profile_employment_status

            branch = emp.department_id.name if emp.department_id else ''

            worksheet.write(row, 0, '', text_center)  # Branch column kept empty
            worksheet.write(row, 1, reason, text_center)
            worksheet.write(row, 2, eyear, text_center)
            worksheet.write(row, 3, emonth, text_center)
            worksheet.write(row, 4, eday, text_center)
            worksheet.write(row, 5, str(dinars), num_center)
            worksheet.write(row, 6, fils_str, text_center)
            worksheet.write(row, 7, family, text_center)
            worksheet.write(row, 8, grandfather, text_center)
            worksheet.write(row, 9, father, text_center)
            worksheet.write(row, 10, first, text_center)
            worksheet.write(row, 11, ssn, text_center)
            worksheet.write(row, 12, str(seq), num_center)

            row += 1
            seq += 1
