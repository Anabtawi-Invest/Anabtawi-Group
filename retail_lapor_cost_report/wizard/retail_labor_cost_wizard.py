# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time
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
    
    # 1. Sales & Profits from POS (Direct Calendar Period Orders: 00:00:00 to 23:59:59)
    sales_profit = fields.Monetary(string='Sales Profit / Revenue', currency_field='currency_id')
    
    # 2. Labor Cost (Actual hr.attendance Presence Days + Approved Overtime Cost)
    employee_count = fields.Integer(string='Employees Count')
    attendance_days = fields.Float(string='Total Attendance Days', digits=(16, 2))
    labor_cost = fields.Monetary(string='Total Labor Cost', currency_field='currency_id')
    
    # 3. Overtime Hours & Financial Cost
    approved_ot_hours = fields.Float(string='Approved Overtime (hrs)', digits=(16, 2))
    approved_ot_cost = fields.Monetary(string='Approved Overtime Cost', currency_field='currency_id')
    unapproved_ot_hours = fields.Float(string='Unapproved Overtime (hrs)', digits=(16, 2))
    total_ot_hours = fields.Float(string='Total Overtime (hrs)', digits=(16, 2))
    
    # Metrics
    labor_pct = fields.Float(string='Labor Cost %', digits=(16, 2))
    pos_config_names = fields.Char(string='Linked POS Configurations')
    currency_id = fields.Many2one('res.currency', string='Currency')
    notes = fields.Char(string='Notes')


class RetailLaborCostWizard(models.TransientModel):
    _name = 'retail.labor.cost.wizard'
    _description = 'Retail Labor Cost & Sales Profit Report Wizard'

    def _default_company(self):
        """Default to the company owning the Retail department if available."""
        dept = self.env['hr.department'].search([
            ('company_id', 'in', self.env.companies.ids),
            '|', '|', '|',
            ('name', '=ilike', 'retail'),
            ('name', '=ilike', 'retail%'),
            ('name', '=ilike', '%retail%'),
            ('name', '=ilike', '%ريتيل%')
        ], limit=1)
        if dept and dept.company_id:
            return dept.company_id
        return self.env.company

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

    @api.model
    def _get_leaf_retail_branches(self, dept_id=None, company_id=None):
        """
        Find only the actual retail branch stores.
        Excludes administration, management, HR, Finance, and grouping region folders.
        """
        dept_id = dept_id or self._default_retail_department()
        if not dept_id:
            return self.env['hr.department']

        dept = self.env['hr.department'].browse(dept_id)
        cid = company_id or (dept.company_id.id if dept else False) or self.env.company.id

        # Look for sub-department 'الفروع' under Retail
        branches_parent = self.env['hr.department'].search([
            ('company_id', '=', cid),
            ('id', 'child_of', dept_id),
            ('name', '=ilike', 'الفروع')
        ], limit=1)
        search_parent = branches_parent.id if branches_parent else dept_id

        all_depts = self.env['hr.department'].search([
            ('company_id', '=', cid),
            ('id', 'child_of', search_parent),
            ('id', '!=', search_parent),
            ('id', '!=', dept_id)
        ])

        # Exclude administrative / non-branch departments and group folders
        ignored_words = ['ادارة', 'إدارة', 'مالية', 'محاسبة', 'موارد بشرية', 'admin', 'hr', 'finance']
        leaf_branches = all_depts.filtered(lambda d:
            not d.child_ids and
            not any(w in (d.name or '').lower() for w in ignored_words)
        )
        return leaf_branches or all_depts

    def _default_branches(self):
        """Pre-select only the actual retail branch departments."""
        branches = self._get_leaf_retail_branches()
        return branches.ids

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=_default_company
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
    total_approved_ot_cost = fields.Monetary(string='Total Approved OT Cost', compute='_compute_totals', currency_field='currency_id')
    total_unapproved_ot = fields.Float(string='Total Unapproved OT (hrs)', compute='_compute_totals', digits=(16, 2))
    total_ot = fields.Float(string='Total OT (hrs)', compute='_compute_totals', digits=(16, 2))
    overall_labor_pct = fields.Float(string='Overall Labor %', compute='_compute_totals', digits=(16, 2))
    currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id')

    file_data = fields.Binary(readonly=True, attachment=False)
    filename = fields.Char(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._populate_preview_lines()
        return records

    @api.onchange('company_id')
    def _onchange_company(self):
        if self.company_id:
            dept = self.env['hr.department'].search([
                ('company_id', '=', self.company_id.id),
                '|', '|', '|',
                ('name', '=ilike', 'retail'),
                ('name', '=ilike', 'retail%'),
                ('name', '=ilike', '%retail%'),
                ('name', '=ilike', '%ريتيل%')
            ], limit=1)
            self.retail_department_id = dept.id if dept else False
            if dept:
                self.branch_department_ids = self._get_leaf_retail_branches(dept.id, self.company_id.id)
            else:
                self.branch_department_ids = False

    @api.onchange('retail_department_id')
    def _onchange_retail_department(self):
        if self.retail_department_id:
            self.branch_department_ids = self._get_leaf_retail_branches(
                self.retail_department_id.id,
                self.company_id.id if self.company_id else False
            )
        else:
            self.branch_department_ids = False

    @api.depends('line_ids', 'line_ids.sales_profit', 'line_ids.labor_cost', 'line_ids.approved_ot_hours', 'line_ids.approved_ot_cost', 'line_ids.unapproved_ot_hours')
    def _compute_totals(self):
        for wiz in self:
            wiz.total_branches = len(wiz.line_ids)
            wiz.total_sales = sum(wiz.line_ids.mapped('sales_profit'))
            wiz.total_labor_cost = sum(wiz.line_ids.mapped('labor_cost'))
            wiz.total_approved_ot = sum(wiz.line_ids.mapped('approved_ot_hours'))
            wiz.total_approved_ot_cost = sum(wiz.line_ids.mapped('approved_ot_cost'))
            wiz.total_unapproved_ot = sum(wiz.line_ids.mapped('unapproved_ot_hours'))
            wiz.total_ot = wiz.total_approved_ot + wiz.total_unapproved_ot
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
        Calculate total branch sales profit reading directly from Point of Sale Orders (pos.order)
        based on the exact calendar date range (date_from 00:00:00 to date_to 23:59:59)
        without shifting into the next day. Matches Point of Sale -> Orders screen totals.
        """
        if not configs:
            return 0.0

        # Method 1: Direct pos.order sales matching POS Orders screen
        orders = self.env['pos.order'].sudo().search([
            ('config_id', 'in', configs.ids),
            ('state', 'in', ('paid', 'done', 'invoiced', 'posted')),
            ('date_order', '>=', str_start),
            ('date_order', '<=', str_end),
        ])
        order_sales = sum(orders.mapped('amount_total'))
        if order_sales:
            return round(order_sales, 3)

        # Method 2: Fallback to pos.payment within exact calendar period
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

    def _get_branch_labor_and_overtime(self, employees, date_from, date_to):
        """
        Calculate Attendance Days, Base Labor Cost, Approved OT Hours, Approved OT Cost,
        and Unapproved OT Hours for branch employees.
        - Overtime cost per employee = employee's approved OT hours * employee's hourly wage.
        - Total labor cost = base attendance cost + total approved OT cost.
        """
        if not employees:
            return 0.0, 0.0, 0.0, 0.0, 0.0

        dt_start = datetime.combine(date_from, time.min)
        dt_end = datetime.combine(date_to, time.max)

        total_base_cost = 0.0
        total_att_days = 0.0
        total_app_ot_hours = 0.0
        total_app_ot_cost = 0.0
        total_unapp_ot_hours = 0.0

        for emp in employees:
            hourly_wage = self._get_employee_hourly_wage(emp)
            hours_per_day = 8.0
            if emp.resource_calendar_id and emp.resource_calendar_id.hours_per_day:
                hours_per_day = emp.resource_calendar_id.hours_per_day
            daily_rate = round(hourly_wage * hours_per_day, 3)

            emp_atts = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', emp.id),
                ('check_in', '>=', dt_start),
                ('check_in', '<=', dt_end),
            ])

            # Attendance Days
            if emp_atts:
                att_days = float(len(set(att.check_in.date() for att in emp_atts if att.check_in)))
            else:
                att_days = 0.0

            emp_cost = round(att_days * daily_rate, 3)
            total_base_cost += emp_cost
            total_att_days += att_days

            # Overtime Hours per employee
            emp_app_ot = 0.0
            emp_unapp_ot = 0.0

            if emp_atts:
                for att in emp_atts:
                    att_app = 0.0
                    att_unapp = 0.0

                    # 1. Linked overtime records (Odoo 19 / planning / custom)
                    if hasattr(att, 'linked_overtime_ids') and att.linked_overtime_ids:
                        for ot in att.linked_overtime_ids:
                            dur = (ot.manual_duration if (hasattr(ot, 'manual_duration') and ot.manual_duration) else ot.duration) or 0.0
                            if getattr(ot, 'status', False) == 'approved':
                                att_app += dur
                            else:
                                att_unapp += dur
                    # 2. Validated Overtime Hours & Overtime Status (Odoo 17/18/19 Enterprise hr_attendance)
                    elif hasattr(att, 'validated_overtime_hours'):
                        val_ot = getattr(att, 'validated_overtime_hours', 0.0) or 0.0
                        raw_ot = getattr(att, 'overtime_hours', 0.0) or 0.0
                        stat = getattr(att, 'overtime_status', False)

                        if stat == 'approved':
                            att_app += (val_ot if val_ot > 0 else raw_ot)
                        elif stat in ('to_approve', 'refused'):
                            att_unapp += raw_ot
                        else:
                            if val_ot > 0:
                                att_app += val_ot
                                if raw_ot > val_ot:
                                    att_unapp += (raw_ot - val_ot)
                            else:
                                att_unapp += raw_ot
                    # 3. Overtime Status field alone
                    elif hasattr(att, 'overtime_status'):
                        raw_ot = getattr(att, 'overtime_hours', 0.0) or getattr(att, 'daily_overtime_hours', 0.0) or 0.0
                        if att.overtime_status == 'approved':
                            att_app += raw_ot
                        else:
                            att_unapp += raw_ot
                    # 4. Fallback when no approval fields exist
                    else:
                        daily_extra = getattr(att, 'daily_overtime_hours', 0.0) or 0.0
                        raw_ot = getattr(att, 'overtime_hours', 0.0) or 0.0
                        att_unapp += (daily_extra or raw_ot)

                    emp_app_ot += att_app
                    emp_unapp_ot += att_unapp

            # Fallback to hr.attendance.overtime.line if attendance records had no overtime but overtime lines exist
            if emp_app_ot == 0.0 and emp_unapp_ot == 0.0 and 'hr.attendance.overtime.line' in self.env:
                ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                ])
                if ot_lines:
                    app_lines = ot_lines.filtered(lambda l: l.status == 'approved')
                    unapp_lines = ot_lines.filtered(lambda l: l.status != 'approved')
                    emp_app_ot = sum((l.manual_duration or l.duration or 0.0) for l in app_lines)
                    emp_unapp_ot = sum((l.manual_duration or l.duration or 0.0) for l in unapp_lines)

            # Financial Cost for APPROVED overtime hours ONLY, multiplied by 1.25 (125% overtime multiplier)
            emp_ot_cost = round(emp_app_ot * hourly_wage * 1.25, 3)

            total_app_ot_hours += emp_app_ot
            total_app_ot_cost += emp_ot_cost
            total_unapp_ot_hours += emp_unapp_ot

        return (
            round(total_base_cost, 3),
            round(total_att_days, 2),
            round(total_app_ot_hours, 2),
            round(total_app_ot_cost, 3),
            round(total_unapp_ot_hours, 2)
        )

    def _prepare_data_rows(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_payroll.group_hr_payroll_user'):
            raise AccessError(_('Only Payroll users may export this report.'))

        # Strictly respect the user's selected branches; do NOT re-add if user removed them!
        branches = self.branch_department_ids
        if not branches or not self.date_from or not self.date_to or self.date_from > self.date_to:
            return []

        # Exact calendar month period: 00:00:00 on date_from to 23:59:59 on date_to (no next day shift)
        dt_start = datetime.combine(self.date_from, time.min)
        dt_end = datetime.combine(self.date_to, time.max)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        rows = []
        for branch in branches:
            branch_code = getattr(branch, 'code', False) or getattr(branch, 'complete_name', False) or str(branch.id)
            branch_name = branch.name or ''

            # 1. Matching POS Configs & Sales Profit (Direct Calendar Orders)
            configs = self._get_branch_pos_configs(branch)
            cfg_names = ', '.join(configs.mapped('name')) if configs else _('Auto/Direct match')
            sales_profit = self._get_branch_sales_profit(configs, str_start, str_end)

            # 2. Employees of this branch (sudo search with fallback to children)
            branch_employees = self.env['hr.employee'].sudo().search([
                ('department_id', '=', branch.id),
                ('company_id', '=', self.company_id.id)
            ])
            if not branch_employees:
                branch_employees = self.env['hr.employee'].sudo().search([
                    ('department_id', 'child_of', branch.id),
                    ('company_id', '=', self.company_id.id)
                ])
            emp_count = len(branch_employees)

            # 3. Labor Cost & Overtime Hours (Calculated per employee from hr.attendance)
            base_labor_cost, att_days, app_ot_hours, app_ot_cost, unapp_ot_hours = self._get_branch_labor_and_overtime(
                branch_employees, self.date_from, self.date_to
            )

            # Total labor cost includes base attendance cost + approved overtime cost!
            total_labor_cost = round(base_labor_cost + app_ot_cost, 3)
            total_ot = round(app_ot_hours + unapp_ot_hours, 2)
            labor_pct = round((total_labor_cost / sales_profit * 100.0), 2) if sales_profit > 0 else 0.0

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
                'labor_cost': total_labor_cost,
                'approved_ot_hours': app_ot_hours,
                'approved_ot_cost': app_ot_cost,
                'unapproved_ot_hours': unapp_ot_hours,
                'total_ot_hours': total_ot,
                'labor_pct': labor_pct,
                'pos_config_names': cfg_names,
                'notes': ' '.join(notes),
            })

        return rows

    def _populate_preview_lines(self):
        """Populate the in-wizard preview table lines and save them in the database for instant display."""
        for wiz in self:
            rows = wiz._prepare_data_rows()
            wiz.line_ids.unlink()
            lines_vals = []
            for r in rows:
                lines_vals.append({
                    'wizard_id': wiz.id,
                    'department_id': r['department_id'],
                    'branch_code': r['branch_code'],
                    'branch_name': r['branch_name'],
                    'company_id': r['company_id'],
                    'sales_profit': r['sales_profit'],
                    'employee_count': r['employee_count'],
                    'attendance_days': r['attendance_days'],
                    'labor_cost': r['labor_cost'],
                    'approved_ot_hours': r['approved_ot_hours'],
                    'approved_ot_cost': r['approved_ot_cost'],
                    'unapproved_ot_hours': r['unapproved_ot_hours'],
                    'total_ot_hours': r['total_ot_hours'],
                    'labor_pct': r['labor_pct'],
                    'pos_config_names': r['pos_config_names'],
                    'currency_id': wiz.company_id.currency_id.id if wiz.company_id.currency_id else False,
                    'notes': r['notes'],
                })
            if lines_vals:
                wiz.env['retail.labor.cost.wizard.line'].create(lines_vals)

    def action_calculate_preview(self):
        """Action button to refresh live calculations inside the wizard preserving user dates and branches."""
        self.ensure_one()
        self._populate_preview_lines()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(
                self.env.context,
                default_company_id=self.company_id.id,
                default_date_from=self.date_from,
                default_date_to=self.date_to,
                default_retail_department_id=self.retail_department_id.id,
                default_branch_department_ids=[(6, 0, self.branch_department_ids.ids)],
            ),
        }

    def action_export_xlsx(self):
        """Generate and download the production Excel report."""
        self.ensure_one()
        rows = self._prepare_data_rows()
        if not rows:
            raise UserError(_('No retail branches or data found for the selected filters.'))

        metadata = {
            'company': self.company_id.name or '',
            'period': f'{self.date_from} to {self.date_to}',
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
