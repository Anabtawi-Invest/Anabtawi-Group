# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools import format_date


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    name_arabic = fields.Char(
        string='Name (Arabic)',
        groups='hr.group_hr_user',
        tracking=True,
    )
    religion = fields.Selection(
        selection=[
            ('muslim', 'Muslim'),
            ('christian', 'Christian'),
            ('other', 'Other'),
        ],
        string='Religion',
        groups='hr.group_hr_user',
        tracking=True,
    )
    mother_name = fields.Char(string="Mother's Name", groups='hr.group_hr_user', tracking=True)
    medical_insurance_ref = fields.Char(
        string='Medical Insurance (override)',
        groups='hr.group_hr_user',
        tracking=True,
        help='If empty, the PDF uses the Health Insurance line of the employee (relationship = Employee): grade and effective date. '
             'Otherwise this text is shown. Separate from blood type.',
    )
    blood_type = fields.Selection(
        selection=[
            ('ap', 'A+'),
            ('an', 'A-'),
            ('bp', 'B+'),
            ('bn', 'B-'),
            ('abp', 'AB+'),
            ('abn', 'AB-'),
            ('op', 'O+'),
            ('on', 'O-'),
            ('other', 'Other'),
        ],
        groups='hr.group_hr_user',
        tracking=True,
    )
    profile_employment_status = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('on_leave', 'On Leave'),
            ('terminated', 'Terminated'),
            ('other', 'Other'),
        ],
        string='Employment Status (Profile)',
        groups='hr.group_hr_user',
        tracking=True,
    )

    warning_line_ids = fields.One2many(
        'hr.employee.warning.line',
        'employee_id',
        string='Warnings',
        groups='hr.group_hr_user',
    )
    previous_job_line_ids = fields.One2many(
        'hr.employee.previous.job.line',
        'employee_id',
        string='Previous Jobs',
        groups='hr.group_hr_user',
    )
    education_line_ids = fields.One2many(
        'hr.employee.education.line',
        'employee_id',
        string='Education',
        groups='hr.group_hr_user',
    )
    official_document_line_ids = fields.One2many(
        'hr.employee.official.document.line',
        'employee_id',
        string='Official Documents',
        groups='hr.group_hr_user',
    )
    career_movement_line_ids = fields.One2many(
        'hr.employee.career.movement.line',
        'employee_id',
        string='Career Movements',
        groups='hr.group_hr_user',
    )
    company_loan_attachment_ids = fields.Many2many(
        'hr.salary.attachment',
        compute='_compute_company_loan_attachments',
        string='Company Loans',
        groups='hr.group_hr_user',
    )
    profile_contract_start_date = fields.Date(
        string='Contract Start Date',
        compute='_compute_profile_contract_dates',
        groups='hr.group_hr_user',
    )
    profile_contract_end_date = fields.Date(
        string='Contract End Date',
        compute='_compute_profile_contract_dates',
        groups='hr.group_hr_user',
    )

    def _compute_profile_contract_dates(self):
        for emp in self:
            start = (
                getattr(emp, 'contract_date_start', False)
                or getattr(emp, 'first_contract_date', False)
                or getattr(emp, 'date_start', False)
            )
            if not start and hasattr(emp, 'contract_id') and emp.contract_id:
                start = emp.contract_id.date_start
            emp.profile_contract_start_date = start or False

            end = (
                getattr(emp, 'contract_date_end', False)
                or getattr(emp, 'date_end', False)
            )
            if not end and hasattr(emp, 'contract_id') and emp.contract_id:
                end = emp.contract_id.date_end
            if not end and 'hr.version' in self.env:
                # date_start/date_end are computed; order/filter on stored contract dates
                v = self.env['hr.version'].sudo().search(
                    [('employee_id', '=', emp.id), ('contract_date_start', '!=', False)],
                    order='contract_date_start desc, id desc', limit=1,
                )
                if v:
                    end = v.contract_date_end or False
            emp.profile_contract_end_date = end or False

    def _compute_company_loan_attachments(self):
        for employee in self:
            employee.company_loan_attachment_ids = employee._get_company_loan_records()

    def _get_company_loan_records(self):
        self.ensure_one()
        if 'hr.salary.attachment' not in self.env:
            return self.env['hr.salary.attachment']

        Attachment = self.env['hr.salary.attachment'].sudo()
        fields_dict = Attachment._fields

        if 'employee_ids' in fields_dict:
            domain = [('employee_ids', 'in', self.id)]
        elif 'employee_id' in fields_dict:
            domain = [('employee_id', '=', self.id)]
        else:
            return self.env['hr.salary.attachment']

        records = Attachment.search(domain, order='date_start desc, id desc')
        loan_ids = []
        for att in records:
            is_company_loan = False
            for input_field in ['other_input_type_id', 'input_type_id', 'payslip_input_type_id']:
                if input_field in fields_dict:
                    input_val = getattr(att, input_field, False)
                    if input_val:
                        code = getattr(input_val, 'code', '') or ''
                        name = getattr(input_val, 'name', '') or ''
                        if code.lower() == 'com_lon' or 'company loan' in name.lower() or 'سلفة' in name:
                            is_company_loan = True
                            break

            if not is_company_loan:
                for type_field in ['deduction_type_id', 'attachment_type_id', 'type_id']:
                    if type_field in fields_dict:
                        type_val = getattr(att, type_field, False)
                        if type_val:
                            code = getattr(type_val, 'code', '') or ''
                            name = getattr(type_val, 'name', '') or ''
                            if code.lower() == 'com_lon' or 'company loan' in name.lower() or 'loan' in name.lower() or 'سلفة' in name:
                                is_company_loan = True
                                break

            if not is_company_loan and getattr(att, 'description', None):
                desc = att.description.lower()
                if 'company loan' in desc or 'advance' in desc or 'سلفة' in desc:
                    is_company_loan = True

            if is_company_loan:
                loan_ids.append(att.id)

        return Attachment.browse(loan_ids)

    def profile_company_loans(self):
        """Returns list of dicts representing company loan salary adjustments for the employee PDF report.
        Includes start date, starting amount, monthly deduction, remaining balance, and status/note.
        """
        self.ensure_one()
        records = self._get_company_loan_records()
        loan_data = []
        for att in records:
            state = getattr(att, 'state', 'open')
            fields_dict = att._fields

            date_start = getattr(att, 'date_start', None)
            total_amount = getattr(att, 'total_amount', 0.0) or getattr(att, 'monthly_amount', 0.0) or 0.0
            monthly_amount = getattr(att, 'monthly_amount', 0.0) or 0.0

            if 'remaining_amount' in fields_dict:
                remaining_amount = att.remaining_amount
            elif 'remaining_total' in fields_dict:
                remaining_amount = att.remaining_total
            elif 'paid_amount' in fields_dict:
                remaining_amount = max(0.0, total_amount - (att.paid_amount or 0.0))
            else:
                remaining_amount = total_amount

            loan_data.append({
                'id': att.id,
                'date_start': date_start,
                'date_start_formatted': format_date(self.env, date_start) if date_start else '',
                'total_amount': total_amount,
                'monthly_amount': monthly_amount,
                'remaining_amount': remaining_amount,
                'note': getattr(att, 'description', '') or '',
                'state': state,
            })
        return loan_data

    def profile_contract_start_display(self):
        """Returns formatted contract start date."""
        self.ensure_one()
        start_date = self.profile_contract_start_date
        return format_date(self.env, start_date) if start_date else ''

    def profile_contract_end_label(self):
        """Returns dynamic label for the contract end / departure date cell."""
        self.ensure_one()
        if self.profile_employment_status == 'terminated':
            return 'Termination Date'
        return 'End Date'

    def profile_contract_end_display(self):
        """Displays contract end date or termination departure date based on employment status:
        - If active and no end date on contract: returns '' (will not show).
        - If active and contract has end date: returns formatted end date.
        - If terminated: returns official departure/termination date or contract end date.
        """
        self.ensure_one()
        if self.profile_employment_status == 'terminated':
            end_date = getattr(self, 'departure_date', False) or self.profile_contract_end_date
            return format_date(self.env, end_date) if end_date else ''

        if self.profile_employment_status == 'active':
            if self.profile_contract_end_date:
                return format_date(self.env, self.profile_contract_end_date)
            return ''

        # Other statuses (suspended, on_leave, etc.)
        other_end = getattr(self, 'departure_date', False) or self.profile_contract_end_date
        return format_date(self.env, other_end) if other_end else ''

    def action_print_employee_profile_pdf(self):
        self.ensure_one()
        return self.env.ref(
            'anabtawi_employee_profile.action_report_employee_profile'
        ).report_action(self)

    def profile_primary_bank_account(self):
        self.ensure_one()
        if self.primary_bank_account_id:
            return self.primary_bank_account_id
        return self.bank_account_ids[:1]

    def profile_health_insurance_header_display(self):
        """PDF header: manual ref, else summary from hr_health_insurance employee line."""
        self.ensure_one()
        if self.medical_insurance_ref:
            return self.medical_insurance_ref
        line = self.health_insurance_ids.filtered(
            lambda r: r.relationship == 'employee'
        )[:1]
        if not line:
            return ''
        parts = []
        if line.grade_id:
            parts.append(line.grade_id.name or '')
        if line.effective_date:
            parts.append(format_date(self.env, line.effective_date))
        return ' — '.join(p for p in parts if p)

    def profile_blood_type_display(self):
        self.ensure_one()
        if not self.blood_type:
            return ''
        field = self._fields['blood_type']
        selection = field.selection
        if callable(selection):
            selection = selection(self)
        return dict(selection).get(self.blood_type) or self.blood_type

    def profile_status_display(self):
        self.ensure_one()
        if not self.profile_employment_status:
            return ''
        field = self._fields['profile_employment_status']
        selection = field.selection
        if callable(selection):
            selection = selection(self)
        return dict(selection).get(self.profile_employment_status) or self.profile_employment_status

    def profile_marital_display(self):
        self.ensure_one()
        if not self.marital:
            return ''
        field = self._fields['marital']
        selection = field.selection
        if callable(selection):
            selection = selection(self)
        return dict(selection).get(self.marital) or self.marital

    def profile_sex_display(self):
        self.ensure_one()
        if not self.sex:
            return ''
        field = self._fields['sex']
        selection = field.selection
        if callable(selection):
            selection = selection(self)
        return dict(selection).get(self.sex) or self.sex

    def profile_religion_display(self):
        self.ensure_one()
        if not self.religion:
            return ''
        field = self._fields['religion']
        selection = field.selection
        if callable(selection):
            selection = selection(self)
        return dict(selection).get(self.religion) or self.religion
