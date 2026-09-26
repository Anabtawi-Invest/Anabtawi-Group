# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time, timedelta
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from .retail_labor_cost_xlsx import build_retail_labor_cost_xlsx

_logger = logging.getLogger(__name__)


class RetailLaborCostWizardLine(models.TransientModel):
    _name = 'retail.labor.cost.wizard.line'
    _description = 'Retail Labor Cost Wizard Line'

    wizard_id = fields.Many2one('retail.labor.cost.wizard', string='Wizard', ondelete='cascade', required=True)
    department_id = fields.Many2one('hr.department', string='Branch Department', required=True)
    branch_code = fields.Char(string='Branch Code')
    branch_name = fields.Char(string='Branch Name')
    company_id = fields.Many2one('res.company', string='Company')
    
    # 1. Sales & Profits from POS
    sales_profit = fields.Monetary(string='Sales Profit / Revenue', currency_field='currency_id')
    
    # 2. Labor Cost
    employee_count = fields.Integer(string='Employees Count')
    attendance_days = fields.Float(string='Total Attendance Days', digits=(16, 2))
    labor_cost = fields.Monetary(string='Total Labor Cost', currency_field='currency_id')
    
    # 3. Overtime Hours
    approved_ot_hours = fields.Float(string='Approved Overtime (hrs)', digits=(16, 2))
    unapproved_ot_hours = fields.Float(string='Unapproved Overtime (hrs)', digits=(16, 2))
    total_ot_hours = fields.Float(string='Total Overtime (hrs)', digits=(16, 2))
    
    # Metrics
    net_margin = fields.Monetary(string='Net Contribution Margin', currency_field='currency_id')
    labor_pct = fields.Float(string='Labor Cost %', digits=(16, 2))
    pos_config_names = fields.Char(string='Linked POS Configurations')
    currency_id = fields.Many2one('res.currency', string='Currency')
    notes = fields.Char(string='Notes')


class RetailLaborCostWizard(models.TransientModel):
    _name = 'retail.labor.cost.wizard'
    _description = 'Retail Labor Cost & Sales Profit Report Wizard'

    def _default_retail_department(self):
        """Find the main Retail department."""
        dept = self.env['hr.department'].search([
            ('company_id', 'in', self.env.companies.ids),
            '|', '|', '|',
            ('name', '=ilike', 'retail'),
            ('name', '=ilike', 'retail%'),
            ('name', '=ilike', '%retail%'),
            ('name', '=ilike', '%ريتيل%')
        ], limit=1)
        return dept.id if dept else False

    def _default_branches(self):
        """Pre-select all child branch departments under Retail."""
        dept_id = self._default_retail_department()
        if dept_id:
            children = self.env['hr.department'].search([
                ('id', 'child_of', dept_id),
                ('id', '!=', dept_id)
            ])
            return children.ids if children else [dept_id]
        return []

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

    retail_department_id = fields.Many2one(
        'hr.department', string='Retail Main Department',
        default=_default_retail_department,
        help="The parent Retail department under which branch departments reside."
    )
    branch_department_ids = fields.Many2many(
        'hr.department', 'retail_labor_wizard_dept_rel', 'wizard_id', 'department_id',
        string='Retail Branches / الأفرع',
        default=_default_branches,
        help="Select the retail branches to include in the report."
    )

    line_ids = fields.One2many(
        'retail.labor.cost.wizard.line', 'wizard_id', string='Branch Cost Lines'
    )

    # KPI Banner Summaries
    total_branches = fields.Integer(string='Total Branches', compute='_compute_totals')
    total_sales = fields.Monetary(string='Total Sales Revenue', compute='_compute_totals', currency_field='currency_id')
    total_labor_cost = fields.Monetary(string='Total Labor Cost', compute='_compute_totals', currency_field='currency_id')
    total_approved_ot = fields.Float(string='Total Approved OT (hrs)', compute='_compute_totals', digits=(16, 2))
    total_unapproved_ot = fields.Float(string='Total Unapproved OT (hrs)', compute='_compute_totals', digits=(16, 2))
    total_ot = fields.Float(string='Total OT (hrs)', compute='_compute_totals', digits=(16, 2))
    overall_net_margin = fields.Monetary(string='Overall Net Margin', compute='_compute_totals', currency_field='currency_id')
    overall_labor_pct = fields.Float(string='Overall Labor %', compute='_compute_totals', digits=(16, 2))
    currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id')

    file_data = fields.Binary(readonly=True, attachment=False)
    filename = fields.Char(readonly=True)

    @api.onchange('retail_department_id')
    def _onchange_retail_department(self):
        if self.retail_department_id:
            children = self.env['hr.department'].search([
                ('id', 'child_of', self.retail_department_id.id),
                ('id', '!=', self.retail_department_id.id)
            ])
            self.branch_department_ids = children if children else self.retail_department_id
        else:
            self.branch_department_ids = False

    @api.onchange('payrun_id')
    def _onchange_payrun(self):
        if self.payrun_id:
            if self.payrun_id.date_start:
                self.date_from = self.payrun_id.date_start
            if self.payrun_id.date_end:
                self.date_to = self.payrun_id.date_end

    @api.onchange('company_id', 'date_from', 'date_to', 'payrun_id', 'retail_department_id', 'branch_department_ids')
    def _onchange_filters(self):
        self._populate_preview_lines()

    @api.depends('line_ids', 'line_ids.sales_profit', 'line_ids.labor_cost', 'line_ids.approved_ot_hours', 'line_ids.unapproved_ot_hours')
    def _compute_totals(self):
        for wiz in self:
            wiz.total_branches = len(wiz.line_ids)
            wiz.total_sales = sum(wiz.line_ids.mapped('sales_profit'))
            wiz.total_labor_cost = sum(wiz.line_ids.mapped('labor_cost'))
            wiz.total_approved_ot = sum(wiz.line_ids.mapped('approved_ot_hours'))
            wiz.total_unapproved_ot = sum(wiz.line_ids.mapped('unapproved_ot_hours'))
            wiz.total_ot = wiz.total_approved_ot + wiz.total_unapproved_ot
            wiz.overall_net_margin = wiz.total_sales - wiz.total_labor_cost
            wiz.overall_labor_pct = round((wiz.total_labor_cost / wiz.total_sales * 100.0), 2) if wiz.total_sales > 0 else 0.0

    # -------------------------------------------------------------------------
    # Business Calculations Engine
    # -------------------------------------------------------------------------
    def _get_branch_pos_configs(self, department):
        """Map a branch department to its corresponding pos.config records."""
        all_configs = self.env['pos.config'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', self.company_id.id)
        ])
        matched_configs = self.env['pos.config']
        dept_name = (department.name or '').strip().lower()
        dept_code = (getattr(department, 'code', False) or '').strip().lower()

        # Clean noise words
        clean_dept = dept_name.replace('فرع', '').replace('branch', '').replace('retail', '').replace('ريتيل', '').replace('-', '').strip()

        for cfg in all_configs:
            cfg_name = (cfg.name or '').strip().lower()
            clean_cfg = cfg_name.replace('فرع', '').replace('branch', '').replace('retail', '').replace('ريتيل', '').replace('-', '').strip()

            # Exact or clean substring match
            if cfg_name == dept_name or (clean_dept and clean_dept == clean_cfg):
                matched_configs |= cfg
            elif clean_dept and (clean_dept in clean_cfg or clean_cfg in clean_dept):
                matched_configs |= cfg
            elif dept_code and dept_code in cfg_name:
                matched_configs |= cfg

        return matched_configs

    def _get_branch_sales_profit(self, configs, str_start, str_end):
        """
        Calculate total branch sales revenue / profits directly matching
        the logic of anabtawi_pos_reporting_dashboard.
        """
        if not configs:
            return 0.0

        # Method A: via pos.payment (preferred in pos_reporting_dashboard for reconciled payments)
        payments = self.env['pos.payment'].sudo().search([
            ('pos_order_id.state', 'in', ('paid', 'done', 'invoiced')),
            ('session_id.config_id', 'in', configs.ids),
            '|',
            '&', ('payment_date', '>=', str_start), ('payment_date', '<=', str_end),
            '&', ('payment_date', '=', False),
                 '&', ('pos_order_id.date_order', '>=', str_start), ('pos_order_id.date_order', '<=', str_end),
        ])
        total_payment_sales = sum(payments.mapped('amount'))

        # Method B: via pos.order direct check
        orders = self.env['pos.order'].sudo().search([
            ('config_id', 'in', configs.ids),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('date_order', '>=', str_start),
            ('date_order', '<=', str_end),
        ])
        total_order_sales = sum(orders.mapped('amount_total'))

        return max(total_payment_sales, total_order_sales)

    def _get_employee_hourly_wage(self, emp, slip=None):
        """Technical field hourly_wage from hr.employee with robust fallbacks."""
        wage = getattr(emp, 'hourly_wage', 0.0)
        if wage:
            return float(wage)
        if slip and hasattr(slip, 'version_id') and slip.version_id:
            v_wage = getattr(slip.version_id, 'hourly_wage', 0.0)
            if v_wage:
                return float(v_wage)
        if slip and slip.contract_id:
            c_wage = getattr(slip.contract_id, 'hourly_wage', 0.0)
            if c_wage:
                return float(c_wage)
        if getattr(emp, 'contract_id', False):
            c_wage = getattr(emp.contract_id, 'hourly_wage', 0.0)
            if c_wage:
                return float(c_wage)
        monthly_wage = (
            getattr(slip, 'wage', 0.0) if slip else 0.0
        ) or getattr(emp, 'wage', 0.0) or (
            getattr(slip.contract_id, 'wage', 0.0) if (slip and slip.contract_id) else 0.0
        )
        if monthly_wage:
            return round(float(monthly_wage) / 240.0, 3)
        return 0.0

    def _get_branch_labor_cost(self, employees, date_from, date_to, payrun_id=None):
        """
        Calculate total labor cost for all employees in a branch:
        Cost = Attendance Days * (hourly_wage * 8.0 hrs/day).
        """
        if not employees:
            return 0.0, 0.0

        payslip_domain = [
            ('employee_id', 'in', employees.ids),
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'cancel'),
        ]
        if payrun_id:
            payslip_domain.append(('payslip_run_id', '=', payrun_id.id))
        else:
            payslip_domain.extend([('date_from', '>=', date_from), ('date_to', '<=', date_to)])

        slips = self.env['hr.payslip'].search(payslip_domain)
        slips_by_emp = {slip.employee_id.id: slip for slip in slips}

        total_cost = 0.0
        total_att_days = 0.0

        absence_codes = {'ABS', 'ABSENT', 'LEAVEUNPAID', 'UN_PAID', 'un_paid', 'SICKLEAVE0', 'LAT', 'OUT', 'UNP', 'OUTCON', 'OUT_OF_CONTRACT'}
        extra_codes = {'EXTRA', 'EXTRA_HOURS', 'OVERTIME', 'OVER_TIME', 'EXTRA100'}

        for emp in employees:
            slip = slips_by_emp.get(emp.id)
            hourly_wage = self._get_employee_hourly_wage(emp, slip)
            hours_per_day = 8.0
            if emp.resource_calendar_id and emp.resource_calendar_id.hours_per_day:
                hours_per_day = emp.resource_calendar_id.hours_per_day
            daily_rate = round(hourly_wage * hours_per_day, 3)

            att_days = 0.0
            if slip and slip.worked_days_line_ids:
                att_lines = slip.worked_days_line_ids.filtered(lambda wd: (
                    (wd.code and wd.code.strip().upper() in ('WORK100', 'ATTENDANCE', 'ATT', 'WORK'))
                    or (wd.work_entry_type_id and 'attendance' in (wd.work_entry_type_id.name or '').lower())
                    or ('attendance' in (wd.name or '').lower())
                    or ('حضور' in (wd.name or '').lower())
                ))
                if not att_lines:
                    att_lines = slip.worked_days_line_ids.filtered(lambda wd: (
                        (wd.code or '').strip().upper() not in absence_codes and
                        (wd.code or '').strip().upper() not in extra_codes and
                        'extra' not in (wd.name or '').lower() and
                        'overtime' not in (wd.name or '').lower() and
                        'out of contract' not in (wd.name or '').lower() and
                        'خارج العقد' not in (wd.name or '').lower() and
                        wd.number_of_days > 0
                    ))
                att_days = sum(att_lines.mapped('number_of_days'))

            emp_cost = round(att_days * daily_rate, 3)
            total_cost += emp_cost
            total_att_days += att_days

        return round(total_cost, 3), round(total_att_days, 2)

    def _get_branch_overtime_hours(self, employees, date_from, date_to):
        """
        Calculate total Overtime Hours for all employees in a branch:
        - Approved Overtime Hours
        - Unapproved Overtime Hours
        """
        if not employees:
            return 0.0, 0.0

        approved_hrs = 0.0
        unapproved_hrs = 0.0

        # Source 1: hr.attendance.overtime.line
        if 'hr.attendance.overtime.line' in self.env:
            ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', 'in', employees.ids),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ])
            for line in ot_lines:
                dur = line.manual_duration if hasattr(line, 'manual_duration') and line.manual_duration else (line.duration or 0.0)
                if line.status == 'approved':
                    approved_hrs += dur
                else:
                    unapproved_hrs += dur

        # Source 2: hr.attendance fallback
        elif 'hr.attendance' in self.env:
            dt_start = datetime.combine(date_from, time.min)
            dt_end = datetime.combine(date_to, time.max)
            attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', 'in', employees.ids),
                ('check_in', '>=', dt_start),
                ('check_in', '<=', dt_end),
            ])
            for att in attendances:
                val_ot = getattr(att, 'validated_overtime_hours', 0.0) or 0.0
                tot_ot = getattr(att, 'overtime_hours', 0.0) or 0.0
                approved_hrs += val_ot
                unapproved_hrs += max(0.0, tot_ot - val_ot)

        return round(approved_hrs, 2), round(unapproved_hrs, 2)

    def _prepare_data_rows(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_payroll.group_hr_payroll_user'):
            raise AccessError(_('Only Payroll users may export this report.'))

        branches = self.branch_department_ids
        if not branches and self.retail_department_id:
            branches = self.env['hr.department'].search([
                ('id', 'child_of', self.retail_department_id.id),
                ('id', '!=', self.retail_department_id.id)
            ])
            if not branches:
                branches = self.retail_department_id

        if not branches:
            branches = self.env['hr.department'].search([
                ('company_id', '=', self.company_id.id),
                '|', ('name', 'ilike', 'retail'), ('name', 'ilike', 'فرع')
            ])

        # Store shift window 06:00 to 05:00 next day
        dt_start = datetime.combine(self.date_from, time(6, 0, 0))
        dt_end = datetime.combine(self.date_to + timedelta(days=1), time(5, 0, 0))
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        rows = []
        for branch in branches:
            branch_code = getattr(branch, 'code', False) or getattr(branch, 'complete_name', False) or str(branch.id)
            branch_name = branch.name or ''

            # 1. Matching POS Configs & Sales Profit
            configs = self._get_branch_pos_configs(branch)
            cfg_names = ', '.join(configs.mapped('name')) if configs else _('Auto/Direct match')
            sales_profit = self._get_branch_sales_profit(configs, str_start, str_end)

            # 2. Employees of this branch
            branch_employees = self.env['hr.employee'].search([
                ('department_id', '=', branch.id),
                ('company_id', '=', self.company_id.id)
            ])
            emp_count = len(branch_employees)

            # 3. Labor Cost
            labor_cost, att_days = self._get_branch_labor_cost(
                branch_employees, self.date_from, self.date_to, self.payrun_id
            )

            # 4. Overtime Hours (Approved vs Unapproved)
            app_ot, unapp_ot = self._get_branch_overtime_hours(
                branch_employees, self.date_from, self.date_to
            )
            total_ot = round(app_ot + unapp_ot, 2)

            # 5. Margins
            net_margin = round(sales_profit - labor_cost, 3)
            labor_pct = round((labor_cost / sales_profit * 100.0), 2) if sales_profit > 0 else 0.0

            notes = []
            if not configs:
                notes.append(_('No matching POS config found by name.'))
            if emp_count == 0:
                notes.append(_('No employees assigned to this branch department.'))
            if sales_profit == 0.0:
                notes.append(_('No POS sales recorded for period.'))

            rows.append({
                'department_id': branch.id,
                'branch_code': branch_code,
                'branch_name': branch_name,
                'company_id': self.company_id.id,
                'sales_profit': sales_profit,
                'employee_count': emp_count,
                'attendance_days': att_days,
                'labor_cost': labor_cost,
                'approved_ot_hours': app_ot,
                'unapproved_ot_hours': unapp_ot,
                'total_ot_hours': total_ot,
                'net_margin': net_margin,
                'labor_pct': labor_pct,
                'pos_config_names': cfg_names,
                'notes': ' '.join(notes),
            })

        return rows

    def _populate_preview_lines(self):
        """Populate line_ids for immediate interactive preview in wizard form."""
        lines_data = []
        rows = self._prepare_data_rows()
        for r in rows:
            lines_data.append((0, 0, {
                'department_id': r['department_id'],
                'branch_code': r['branch_code'],
                'branch_name': r['branch_name'],
                'company_id': r['company_id'],
                'sales_profit': r['sales_profit'],
                'employee_count': r['employee_count'],
                'attendance_days': r['attendance_days'],
                'labor_cost': r['labor_cost'],
                'approved_ot_hours': r['approved_ot_hours'],
                'unapproved_ot_hours': r['unapproved_ot_hours'],
                'total_ot_hours': r['total_ot_hours'],
                'net_margin': r['net_margin'],
                'labor_pct': r['labor_pct'],
                'pos_config_names': r['pos_config_names'],
                'currency_id': self.company_id.currency_id.id,
                'notes': r['notes'],
            }))
        self.line_ids = [(5, 0, 0)] + lines_data

    def action_calculate_preview(self):
        """Explicit action to calculate/refresh the preview inside the wizard pop-up."""
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
            raise UserError(_('No retail branches found matching the selected criteria.'))

        metadata = {
            'company': self.company_id.name or '',
            'period': f'{self.date_from} — {self.date_to}',
            'payrun': self.payrun_id.name if self.payrun_id else _('All Pay Runs'),
            'user': self.env.user.name or '',
            'currency': self.company_id.currency_id.name or 'JOD',
            'generated': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%Y-%m-%d %H:%M'),
        }

        content = build_retail_labor_cost_xlsx(rows, metadata)
        fname = f"Retail_Labor_Cost_Report_{self.date_from}_{self.date_to}.xlsx"
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
            menu = self.env.ref('retail_lapor_cost_report.menu_retail_labor_cost_report', raise_if_not_found=False)
            if menu:
                menu.write({'parent_id': parent.id})
