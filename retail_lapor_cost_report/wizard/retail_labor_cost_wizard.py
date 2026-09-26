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
    branch_name = fields.Char(string='Branch Name / اسم الفرع')
    company_id = fields.Many2one('res.company', string='Company')
    
    # 1. Sales & Profits from POS (Standard Calendar Period Orders)
    sales_profit = fields.Monetary(string='Sales Profit / Revenue', currency_field='currency_id')
    
    # 2. Labor Cost (Actual Attendance Days)
    employee_count = fields.Integer(string='Employees Count')
    attendance_days = fields.Float(string='Total Attendance Days', digits=(16, 2))
    labor_cost = fields.Monetary(string='Total Labor Cost', currency_field='currency_id')
    
    # 3. Overtime Hours (Attendance Screen: Daily Extra Hours vs Extra Hours)
    approved_ot_hours = fields.Float(string='Approved Overtime (hrs)', digits=(16, 2))
    unapproved_ot_hours = fields.Float(string='Unapproved Overtime (hrs)', digits=(16, 2))
    total_ot_hours = fields.Float(string='Total Overtime (hrs)', digits=(16, 2))
    
    # Metrics
    net_margin = fields.Monetary(string='Net Contribution Margin', currency_field='currency_id')
    labor_pct = fields.Float(string='Labor Cost %', digits=(16, 2))
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

    @api.onchange('company_id', 'date_from', 'date_to', 'retail_department_id', 'branch_department_ids')
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

        clean_dept = dept_name.replace('فرع', '').replace('branch', '').replace('retail', '').replace('ريتيل', '').replace('-', '').strip()

        for cfg in all_configs:
            cfg_name = (cfg.name or '').strip().lower()
            clean_cfg = cfg_name.replace('فرع', '').replace('branch', '').replace('retail', '').replace('ريتيل', '').replace('-', '').strip()

            if cfg_name == dept_name or (clean_dept and clean_dept == clean_cfg):
                matched_configs |= cfg
            elif clean_dept and (clean_dept in clean_cfg or clean_cfg in clean_dept):
                matched_configs |= cfg
            elif dept_code and dept_code in cfg_name:
                matched_configs |= cfg

        return matched_configs

    def _get_branch_sales_profit(self, configs, str_start, str_end):
        """
        Calculate total branch sales revenue reading directly from Point of Sale Orders (pos.order)
        based on the exact calendar date range (date_from 00:00:00 to date_to 23:59:59).
        Matches Point of Sale -> Orders screen totals.
        """
        if not configs:
            return 0.0

        orders = self.env['pos.order'].sudo().search([
            ('config_id', 'in', configs.ids),
            ('state', 'in', ('paid', 'done', 'invoiced', 'posted')),
            ('date_order', '>=', str_start),
            ('date_order', '<=', str_end),
        ])
        order_sales = sum(orders.mapped('amount_total'))
        if order_sales:
            return round(order_sales, 3)

        # Fallback to pos.payment if needed
        payments = self.env['pos.payment'].sudo().search([
            ('session_id.config_id', 'in', configs.ids),
            ('pos_order_id.state', 'in', ('paid', 'done', 'invoiced')),
            ('payment_date', '>=', str_start),
            ('payment_date', '<=', str_end),
        ])
        return round(sum(payments.mapped('amount')), 3)

    def _get_employee_hourly_wage(self, emp):
        """Technical field hourly_wage from hr.employee with contract/wage fallbacks."""
        wage = getattr(emp, 'hourly_wage', 0.0)
        if wage:
            return float(wage)
        if getattr(emp, 'contract_id', False):
            c_wage = getattr(emp.contract_id, 'hourly_wage', 0.0)
            if c_wage:
                return float(c_wage)
        monthly_wage = getattr(emp, 'wage', 0.0) or (
            getattr(emp.contract_id, 'wage', 0.0) if getattr(emp, 'contract_id', False) else 0.0
        )
        if monthly_wage:
            return round(float(monthly_wage) / 240.0, 3)
        return 0.0

    def _get_branch_labor_cost(self, employees, date_from, date_to):
        """
        Calculate total Attendance Days and Labor Cost for all employees in a branch:
        Reads directly from hr.attendance actual physical check-ins during the period.
        - Attendance Days = count of distinct days each employee actually attended work.
        - Daily Rate = hourly_wage * 8.0 hrs/day (or resource calendar hours).
        - Labor Cost = sum of (emp_att_days * daily_rate) for each employee.
        """
        if not employees:
            return 0.0, 0.0

        dt_start = datetime.combine(date_from, time.min)
        dt_end = datetime.combine(date_to, time.max)

        total_cost = 0.0
        total_att_days = 0.0

        for emp in employees:
            emp_atts = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', emp.id),
                ('check_in', '>=', dt_start),
                ('check_in', '<=', dt_end),
            ])
            if emp_atts:
                # Count distinct check-in dates
                att_days = float(len(set(att.check_in.date() for att in emp_atts if att.check_in)))
            else:
                att_days = 0.0

            hourly_wage = self._get_employee_hourly_wage(emp)
            hours_per_day = 8.0
            if emp.resource_calendar_id and emp.resource_calendar_id.hours_per_day:
                hours_per_day = emp.resource_calendar_id.hours_per_day
            daily_rate = round(hourly_wage * hours_per_day, 3)

            emp_cost = round(att_days * daily_rate, 3)
            total_cost += emp_cost
            total_att_days += att_days

        return round(total_cost, 3), round(total_att_days, 2)

    def _get_branch_overtime_hours(self, employees, date_from, date_to):
        """
        Calculate total Overtime Hours for all employees in a branch:
        Reads directly from hr.attendance matching the Attendance screen columns:
        - Daily Extra Hours (daily_overtime_hours): Total Extra Hours worked.
        - Extra Hours (overtime_hours): Approved Extra Hours.
        - Unapproved Extra Hours = Daily Extra Hours - Extra Hours.
        """
        if not employees:
            return 0.0, 0.0

        dt_start = datetime.combine(date_from, time.min)
        dt_end = datetime.combine(date_to, time.max)

        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('check_in', '>=', dt_start),
            ('check_in', '<=', dt_end),
        ])

        if attendances:
            has_daily = hasattr(attendances[0], 'daily_overtime_hours')
            has_ot = hasattr(attendances[0], 'overtime_hours')

            daily_extra = sum((getattr(att, 'daily_overtime_hours', 0.0) or 0.0) for att in attendances) if has_daily else 0.0
            ot_hours = sum((getattr(att, 'overtime_hours', 0.0) or 0.0) for att in attendances) if has_ot else 0.0

            if daily_extra > 0 and ot_hours > 0:
                if daily_extra >= ot_hours:
                    approved_ot = ot_hours
                    unapproved_ot = daily_extra - ot_hours
                else:
                    approved_ot = daily_extra
                    unapproved_ot = ot_hours - daily_extra
                return round(approved_ot, 2), round(unapproved_ot, 2)
            elif daily_extra > 0:
                return round(daily_extra, 2), 0.0
            elif ot_hours > 0:
                approved = sum(att.overtime_hours for att in attendances if getattr(att, 'overtime_status', '') == 'approved')
                unapproved = sum(att.overtime_hours for att in attendances if getattr(att, 'overtime_status', '') != 'approved')
                if approved == 0 and unapproved == 0:
                    approved = ot_hours
                return round(approved, 2), round(unapproved, 2)

        # Fallback to hr.attendance.overtime.line
        if 'hr.attendance.overtime.line' in self.env:
            ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', 'in', employees.ids),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ])
            approved_hrs = sum(
                (l.manual_duration or l.duration or 0.0) for l in ot_lines if l.status == 'approved'
            )
            unapproved_hrs = sum(
                (l.manual_duration or l.duration or 0.0) for l in ot_lines if l.status != 'approved'
            )
            return round(approved_hrs, 2), round(unapproved_hrs, 2)

        return 0.0, 0.0

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

        # Standard Calendar Month/Period: 00:00:00 on date_from to 23:59:59 on date_to
        dt_start = datetime.combine(self.date_from, time.min)
        dt_end = datetime.combine(self.date_to, time.max)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        rows = []
        for branch in branches:
            branch_name = branch.name or ''

            # 1. Matching POS Configs & Sales Profit (Direct Calendar Orders)
            configs = self._get_branch_pos_configs(branch)
            sales_profit = self._get_branch_sales_profit(configs, str_start, str_end)

            # 2. Employees of this branch
            branch_employees = self.env['hr.employee'].search([
                ('department_id', '=', branch.id),
                ('company_id', '=', self.company_id.id)
            ])
            emp_count = len(branch_employees)

            # 3. Labor Cost & Attendance Days (Actual Attendance Screen Check-ins)
            labor_cost, att_days = self._get_branch_labor_cost(
                branch_employees, self.date_from, self.date_to
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
                'branch_name': branch_name,
                'sales_profit': sales_profit,
                'employee_count': emp_count,
                'attendance_days': att_days,
                'labor_cost': labor_cost,
                'approved_ot_hours': app_ot,
                'unapproved_ot_hours': unapp_ot,
                'total_ot_hours': total_ot,
                'net_margin': net_margin,
                'labor_pct': labor_pct,
                'currency_id': self.company_id.currency_id.id,
                'notes': ' | '.join(notes) if notes else '',
            })

        return rows

    def _populate_preview_lines(self):
        """Populate the in-wizard preview table without saving permanently."""
        self.line_ids.unlink()
        rows = self._prepare_data_rows()
        line_vals = []
        for r in rows:
            line_vals.append((0, 0, {
                'department_id': r['department_id'],
                'branch_name': r['branch_name'],
                'sales_profit': r['sales_profit'],
                'employee_count': r['employee_count'],
                'attendance_days': r['attendance_days'],
                'labor_cost': r['labor_cost'],
                'approved_ot_hours': r['approved_ot_hours'],
                'unapproved_ot_hours': r['unapproved_ot_hours'],
                'total_ot_hours': r['total_ot_hours'],
                'net_margin': r['net_margin'],
                'labor_pct': r['labor_pct'],
                'currency_id': r['currency_id'],
                'notes': r['notes'],
            }))
        self.line_ids = line_vals

    def action_calculate_preview(self):
        """Action button to refresh live calculations inside the wizard."""
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
        """Generate and download the production Excel report."""
        self.ensure_one()
        rows = self._prepare_data_rows()
        if not rows:
            raise UserError(_('No retail branches or data found for the selected filters.'))

        metadata = {
            'company': self.company_id.name or '',
            'period': f'{self.date_from} — {self.date_to}',
            'user': self.env.user.name or '',
            'generated': fields.Datetime.now().strftime('%Y-%m-%d %H:%M'),
            'currency': self.company_id.currency_id.name or 'JOD',
        }

        xlsx_bytes = build_retail_labor_cost_xlsx(rows, metadata)
        fname = f"Retail_Labor_Cost_Report_{self.date_from}_{self.date_to}.xlsx"

        self.write({
            'file_data': base64.b64encode(xlsx_bytes),
            'filename': fname,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model=retail.labor.cost.wizard&id={self.id}&field=file_data&filename={fname}&download=true',
            'target': 'self',
        }

    @api.model
    def _attach_reporting_menu(self):
        """Ensure menu item attaches under Payroll -> Reporting if available."""
        try:
            candidates = [
                'hr_payroll.menu_hr_payroll_report',
                'hr_payroll_community.menu_hr_payroll_report',
                'hr_payroll.payroll_report_menu',
                'hr_payroll.menu_payroll_report',
            ]
            target_parent = None
            for xml_id in candidates:
                menu = self.env.ref(xml_id, raise_if_not_found=False)
                if menu:
                    target_parent = menu
                    break

            if target_parent:
                my_menu = self.env.ref('retail_lapor_cost_report.menu_retail_labor_cost_report', raise_if_not_found=False)
                if my_menu and my_menu.parent_id != target_parent:
                    my_menu.write({'parent_id': target_parent.id})
        except Exception as e:
            _logger.warning("Could not auto-attach retail labor cost report menu: %s", e)
