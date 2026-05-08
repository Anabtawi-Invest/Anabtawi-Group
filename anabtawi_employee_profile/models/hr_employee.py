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
    religion = fields.Char(groups='hr.group_hr_user', tracking=True)
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
