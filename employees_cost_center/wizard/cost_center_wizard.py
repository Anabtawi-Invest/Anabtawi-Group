# -*- coding: utf-8 -*-
import base64
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from .cost_center_xlsx import build_cost_center_xlsx

class EmployeeCostCenterWizardLine(models.TransientModel):
    _name = 'employee.cost.center.wizard.line'
    _description = 'Employee Cost Center Wizard Line'

    wizard_id = fields.Many2one('employee.cost.center.wizard', string='Wizard', ondelete='cascade', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    employee_code = fields.Char(string='Employee ID')
    department_id = fields.Many2one('hr.department', string='Department')
    job_id = fields.Many2one('hr.job', string='Job Position')
    company_id = fields.Many2one('res.company', string='Company')
    payrun_id = fields.Many2one('hr.payslip.run', string='Pay Run')
    payslip_id = fields.Many2one('hr.payslip', string='Payslip')
    payslip_state = fields.Char(string='Payslip Status')
    
    hourly_wage = fields.Monetary(string='Hourly Wage', currency_field='currency_id')
    hours_per_day = fields.Float(string='Daily Hours', default=8.0, digits=(16, 2))
    daily_rate = fields.Monetary(string='Daily Rate', currency_field='currency_id')
    attendance_days = fields.Float(string='Attendance Days', digits=(16, 2))
    attendance_hours = fields.Float(string='Attendance Hours', digits=(16, 2))
    monthly_cost = fields.Monetary(string='Total Monthly Cost', currency_field='currency_id')
    line_amount = fields.Monetary(string='Payslip Attendance Amount', currency_field='currency_id')
    payslip_net = fields.Monetary(string='Payslip Net', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency')
    notes = fields.Char(string='Notes')


class EmployeeCostCenterWizard(models.TransientModel):
    _name = 'employee.cost.center.wizard'
    _description = 'Employee Cost Center Report'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    date_from = fields.Date(
        string='Period From', required=True,
        default=lambda self: fields.Date.start_of(fields.Date.context_today(self), 'month')
    )
    date_to = fields.Date(
        string='Period To', required=True,
        default=lambda self: fields.Date.end_of(fields.Date.context_today(self), 'month')
    )
    payrun_id = fields.Many2one('hr.payslip.run', string='Pay Run')
    department_ids = fields.Many2many('hr.department', string='Departments')
    employee_ids = fields.Many2many('hr.employee', string='Employees')

    line_ids = fields.One2many(
        'employee.cost.center.wizard.line', 'wizard_id', string='Cost Center Preview Lines'
    )

    total_employees = fields.Integer(string='Total Employees', compute='_compute_totals')
    total_attendance_days = fields.Float(string='Total Attendance Days', compute='_compute_totals', digits=(16, 2))
    total_attendance_hours = fields.Float(string='Total Attendance Hours', compute='_compute_totals', digits=(16, 2))
    total_cost = fields.Monetary(string='Total Company Cost', compute='_compute_totals', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id')

    file_data = fields.Binary(readonly=True, attachment=False)
    filename = fields.Char(readonly=True)

    @api.depends('line_ids', 'line_ids.attendance_days', 'line_ids.attendance_hours', 'line_ids.monthly_cost')
    def _compute_totals(self):
        for wiz in self:
            wiz.total_employees = len(wiz.line_ids.mapped('employee_id'))
            wiz.total_attendance_days = sum(wiz.line_ids.mapped('attendance_days'))
            wiz.total_attendance_hours = sum(wiz.line_ids.mapped('attendance_hours'))
            wiz.total_cost = sum(wiz.line_ids.mapped('monthly_cost'))

    @api.onchange('payrun_id')
    def _onchange_payrun(self):
        if self.payrun_id:
            if self.payrun_id.date_start:
                self.date_from = self.payrun_id.date_start
            if self.payrun_id.date_end:
                self.date_to = self.payrun_id.date_end

    @api.onchange('company_id', 'date_from', 'date_to', 'payrun_id', 'department_ids', 'employee_ids')
    def _onchange_filters(self):
        self._populate_preview_lines()

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_('Period From must not be after Period To.'))

    def _get_employee_hourly_wage(self, emp, slip=None):
        """Retrieve hourly_wage with comprehensive fallbacks across Odoo versions."""
        # 1. Direct on hr.employee (technical field requested by user)
        wage = getattr(emp, 'hourly_wage', 0.0)
        if wage:
            return float(wage)

        # 2. Check payslip version_id (Odoo 18/19 Enterprise HR/Payroll)
        if slip and hasattr(slip, 'version_id') and slip.version_id:
            v_wage = getattr(slip.version_id, 'hourly_wage', 0.0)
            if v_wage:
                return float(v_wage)

        # 3. Check payslip contract_id
        if slip and slip.contract_id:
            c_wage = getattr(slip.contract_id, 'hourly_wage', 0.0)
            if c_wage:
                return float(c_wage)

        # 4. Check employee contract_id / version_id
        if getattr(emp, 'contract_id', False):
            c_wage = getattr(emp.contract_id, 'hourly_wage', 0.0)
            if c_wage:
                return float(c_wage)

        # 5. Fallback: Monthly wage converted to hourly rate (Jordanian standard: 240 hours = 30 days * 8 hrs)
        monthly_wage = (
            getattr(slip, 'wage', 0.0) if slip else 0.0
        ) or getattr(emp, 'wage', 0.0) or (
            getattr(slip.contract_id, 'wage', 0.0) if (slip and slip.contract_id) else 0.0
        )
        if monthly_wage:
            return round(float(monthly_wage) / 240.0, 3)

        return 0.0

    def _get_attendance_line_metrics(self, slip):
        """Extract attendance days, hours, and amount from payslip worked days."""
        if not slip or not slip.worked_days_line_ids:
            return 0.0, 0.0, 0.0

        # Exact attendance matching by code or name
        att_lines = slip.worked_days_line_ids.filtered(lambda wd: (
            (wd.code and wd.code.strip().upper() in ('WORK100', 'ATTENDANCE', 'ATT', 'WORK'))
            or (wd.work_entry_type_id and 'attendance' in (wd.work_entry_type_id.name or '').lower())
            or ('attendance' in (wd.name or '').lower())
            or ('حضور' in (wd.name or '').lower())
        ))

        # Fallback: all paid lines excluding absences and extra hours/overtime
        if not att_lines:
            absence_codes = {'ABS', 'ABSENT', 'LEAVEUNPAID', 'UN_PAID', 'un_paid', 'SICKLEAVE0', 'LAT', 'OUT', 'UNP', 'OUTCON', 'OUT_OF_CONTRACT'}
            extra_codes = {'EXTRA', 'EXTRA_HOURS', 'OVERTIME', 'OVER_TIME', 'EXTRA100'}
            att_lines = slip.worked_days_line_ids.filtered(lambda wd: (
                (wd.code or '').strip().upper() not in absence_codes and
                (wd.code or '').strip().upper() not in extra_codes and
                'extra' not in (wd.name or '').lower() and
                'overtime' not in (wd.name or '').lower() and
                'out of contract' not in (wd.name or '').lower() and
                'خارج العقد' not in (wd.name or '').lower() and
                wd.number_of_days > 0
            ))

        days = sum(att_lines.mapped('number_of_days'))
        hours = sum(att_lines.mapped('number_of_hours'))
        amount = sum(att_lines.mapped('amount'))
        return float(days), float(hours), float(amount)

    def _prepare_data_rows(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_payroll.group_hr_payroll_user'):
            raise AccessError(_('Only Payroll users may export this report.'))

        domain = [('company_id', '=', self.company_id.id), ('state', '!=', 'cancel')]
        if self.payrun_id:
            domain.append(('payslip_run_id', '=', self.payrun_id.id))
        else:
            if self.date_from:
                domain.append(('date_from', '>=', self.date_from))
            if self.date_to:
                domain.append(('date_to', '<=', self.date_to))

        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_ids:
            domain.append(('employee_id.department_id', 'in', self.department_ids.ids))

        slips = self.env['hr.payslip'].search(domain, order='employee_id, date_from, id')

        states_dict = dict(self.env['hr.payslip']._fields['state']._description_selection(self.env)) if hasattr(self.env['hr.payslip']._fields['state'], '_description_selection') else {}

        rows = []
        covered_employees = set()

        for slip in slips:
            emp = slip.employee_id
            covered_employees.add(emp.id)

            hourly_wage = self._get_employee_hourly_wage(emp, slip)
            hours_per_day = 8.0
            if emp.resource_calendar_id and emp.resource_calendar_id.hours_per_day:
                hours_per_day = emp.resource_calendar_id.hours_per_day

            daily_rate = round(hourly_wage * hours_per_day, 3)
            att_days, att_hours, att_amount = self._get_attendance_line_metrics(slip)

            # Formula requested: Attendance Days * (hourly_wage * 8)
            monthly_cost = round(att_days * daily_rate, 3)

            emp_code = (
                getattr(emp, 'employee_number', False) or
                getattr(emp, 'registration_number', False) or
                getattr(emp, 'barcode', False) or
                str(emp.id)
            )

            net_sal = getattr(slip, 'net_wage', 0.0) or 0.0
            if not net_sal and slip.line_ids:
                net_sal = sum(slip.line_ids.filtered(lambda l: l.code == 'NET').mapped('total'))

            notes = []
            if not hourly_wage:
                notes.append(_('Hourly wage is not set on employee profile.'))
            if not att_days and not att_hours:
                notes.append(_('No attendance lines found on payslip worked days.'))

            rows.append({
                'employee_id': emp.id,
                'employee_code': emp_code,
                'employee_name': emp.name or '',
                'company_id': slip.company_id.id,
                'company_name': slip.company_id.name or '',
                'department_id': emp.department_id.id if emp.department_id else False,
                'department_name': emp.department_id.name or '',
                'job_id': emp.job_id.id if emp.job_id else False,
                'job_title': emp.job_id.name or '',
                'payrun_id': slip.payslip_run_id.id if slip.payslip_run_id else False,
                'payrun_name': slip.payslip_run_id.name or '',
                'period': f"{slip.date_from} — {slip.date_to}",
                'hourly_wage': hourly_wage,
                'hours_per_day': hours_per_day,
                'daily_rate': daily_rate,
                'attendance_days': att_days,
                'attendance_hours': att_hours,
                'monthly_cost': monthly_cost,
                'line_amount': att_amount,
                'payslip_net': net_sal,
                'payslip_id': slip.id,
                'payslip_status': states_dict.get(slip.state, slip.state),
                'currency_id': slip.company_id.currency_id.id,
                'notes': ' '.join(notes),
            })

        # If user explicitly selected employees who don't have payslips in the period yet, show preview row
        if self.employee_ids:
            missing_emps = self.employee_ids.filtered(lambda e: e.id not in covered_employees)
            for emp in missing_emps:
                hourly_wage = self._get_employee_hourly_wage(emp)
                hours_per_day = 8.0
                if emp.resource_calendar_id and emp.resource_calendar_id.hours_per_day:
                    hours_per_day = emp.resource_calendar_id.hours_per_day
                daily_rate = round(hourly_wage * hours_per_day, 3)

                emp_code = (
                    getattr(emp, 'employee_number', False) or
                    getattr(emp, 'registration_number', False) or
                    getattr(emp, 'barcode', False) or
                    str(emp.id)
                )

                rows.append({
                    'employee_id': emp.id,
                    'employee_code': emp_code,
                    'employee_name': emp.name or '',
                    'company_id': self.company_id.id,
                    'company_name': self.company_id.name or '',
                    'department_id': emp.department_id.id if emp.department_id else False,
                    'department_name': emp.department_id.name or '',
                    'job_id': emp.job_id.id if emp.job_id else False,
                    'job_title': emp.job_id.name or '',
                    'payrun_id': self.payrun_id.id if self.payrun_id else False,
                    'payrun_name': self.payrun_id.name if self.payrun_id else '',
                    'period': f"{self.date_from} — {self.date_to}",
                    'hourly_wage': hourly_wage,
                    'hours_per_day': hours_per_day,
                    'daily_rate': daily_rate,
                    'attendance_days': 0.0,
                    'attendance_hours': 0.0,
                    'monthly_cost': 0.0,
                    'line_amount': 0.0,
                    'payslip_net': 0.0,
                    'payslip_id': False,
                    'payslip_status': _('No Payslip'),
                    'currency_id': self.company_id.currency_id.id,
                    'notes': _('No confirmed/draft payslip found in selected period.'),
                })

        return rows

    def _populate_preview_lines(self):
        """Populate line_ids for immediate interactive preview in wizard form."""
        lines_data = []
        rows = self._prepare_data_rows()
        for r in rows:
            lines_data.append((0, 0, {
                'employee_id': r['employee_id'],
                'employee_code': r['employee_code'],
                'department_id': r['department_id'],
                'job_id': r['job_id'],
                'company_id': r['company_id'],
                'payrun_id': r['payrun_id'],
                'payslip_id': r['payslip_id'],
                'payslip_state': r['payslip_status'],
                'hourly_wage': r['hourly_wage'],
                'hours_per_day': r['hours_per_day'],
                'daily_rate': r['daily_rate'],
                'attendance_days': r['attendance_days'],
                'attendance_hours': r['attendance_hours'],
                'monthly_cost': r['monthly_cost'],
                'line_amount': r['line_amount'],
                'payslip_net': r['payslip_net'],
                'currency_id': r['currency_id'],
                'notes': r['notes'],
            }))
        self.line_ids = [(5, 0, 0)] + lines_data

    def action_calculate_preview(self):
        """Explicit action to calculate/refresh the preview inside the wizard."""
        self.ensure_one()
        self._populate_preview_lines()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_export_xlsx(self):
        """Generate formatted Excel report and trigger download."""
        self.ensure_one()
        rows = self._prepare_data_rows()
        if not rows:
            raise UserError(_('No payslips or employee records found matching the selected filters.'))

        metadata = {
            'company': self.company_id.name or '',
            'period': f'{self.date_from} — {self.date_to}',
            'payrun': self.payrun_id.name if self.payrun_id else _('All Pay Runs'),
            'user': self.env.user.name or '',
            'currency': self.company_id.currency_id.name or 'JOD',
            'generated': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%Y-%m-%d %H:%M'),
        }

        content = build_cost_center_xlsx(rows, metadata)
        fname = f"Employees_Cost_Center_{self.date_from}_{self.date_to}.xlsx"
        self.write({
            'file_data': base64.b64encode(content),
            'filename': fname,
        })

        return {
            'type': 'ir.actions.act_url',
            'target': 'download',
            'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&filename_field=filename&download=true'
        }

    @api.model
    def _attach_reporting_menu(self):
        """Resolve standard Payroll Reporting menu across Odoo distributions."""
        parent = self.env.ref('hr_payroll.menu_hr_payroll_report', raise_if_not_found=False)
        if not parent:
            data = self.env['ir.model.data'].search([
                ('module', '=', 'hr_payroll'),
                ('model', '=', 'ir.ui.menu'),
                ('name', 'ilike', 'report')
            ])
            candidates = self.env['ir.ui.menu'].browse(data.mapped('res_id')).exists().filtered(lambda menu: not menu.action)
            if len(candidates) == 1:
                parent = candidates
        if parent:
            menu = self.env.ref('employees_cost_center.menu_employee_cost_center', raise_if_not_found=False)
            if menu:
                menu.write({'parent_id': parent.id})
