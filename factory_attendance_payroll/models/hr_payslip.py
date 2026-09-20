# -*- coding: utf-8 -*-

from collections import defaultdict
import datetime
import logging
from odoo import models, fields, api
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    attendance_gross_overtime = fields.Float(
        string="Monthly Overtime Earned",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Total overtime hours earned from attendance during the month."
    )
    rest_days_taken = fields.Float(
        string="Rest Days Taken",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Weekly rest/off days taken this month (unworked days excluding public holidays "
             "and approved leave). Monthly allowance is 4; each unused rest day adds "
             "8 × 1.5 hours to Monthly Overtime Earned."
    )
    attendance_gross_undertime = fields.Float(
        string="Monthly Lateness / Undertime",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Total lateness and undertime hours accumulated from attendance during the month."
    )
    total_extra_hours_available = fields.Float(
        string="Total Extra Hours Available",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Previous Extra Hours Balance plus new Monthly Overtime Earned."
    )
    remaining_extra_hours_balance = fields.Float(
        string="Remaining Extra Hours Balance",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Remaining Extra Hours available after settling Step 1 Lateness (Total Available minus Step 1 Settled Lateness)."
    )

    # 3-Step Lateness Settlement Audit Breakdown Fields
    lateness_covered_by_extra_hours = fields.Float(
        string="Step 1: Lateness Deducted from Extra Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Step 1: Lateness hours covered using total available Extra Hours Balance."
    )
    lateness_covered_by_annual_leave = fields.Float(
        string="Step 2: Lateness Deducted from Annual Leave",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Step 2: Lateness hours covered using available Annual Leave balance."
    )
    undertime_cash_deduction_hours = fields.Float(
        string="Step 3: Remaining Lateness Deducted from Cash",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Step 3: Final remaining lateness hours deducted from monthly cash salary."
    )

    # View compatibility aliases
    lateness_covered_by_paid_time_off = fields.Float(
        string="Lateness Covered by Paid Time Off",
        default=0.0
    )
    undertime_covered_by_extra_hours = fields.Float(
        related="lateness_covered_by_extra_hours",
        string="Undertime Settled via Extra Hours",
        store=True
    )
    undertime_covered_by_annual_leave = fields.Float(
        related="lateness_covered_by_annual_leave",
        string="Undertime Settled via Annual Leave",
        store=True
    )
    attendance_net_reconciled = fields.Float(
        string="Net Reconciled Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True
    )
    is_reconciled = fields.Boolean(
        string="Attendance Reconciled",
        default=False,
        copy=False,
        help="Tracks whether attendance reconciliation and leave settlements have already been applied for this payslip."
    )
    extra_hours_allocated_days = fields.Float(
        string="Extra Hours Added to Allocation",
        default=0.0,
        copy=False,
        help="Tracks duration in days added directly to employee's Extra Hours allocation by this payslip."
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        if not getattr(self.env.registry, 'ready', True) or self.env.context.get('install_mode') or self.env.context.get('module_installation') or self.env.context.get('tracking_disable'):
            self.attendance_gross_overtime = 0.0
            self.rest_days_taken = 0.0
            self.attendance_gross_undertime = 0.0
            self.attendance_net_reconciled = 0.0
            self.total_extra_hours_available = 0.0
            self.lateness_covered_by_extra_hours = 0.0
            self.lateness_covered_by_annual_leave = 0.0
            self.remaining_extra_hours_balance = 0.0
            self.undertime_cash_deduction_hours = 0.0
            return

        valid_slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to and (s.state in ['draft', 'verify'] or not s.id))
        
        other_slips = self - valid_slips
        if other_slips:
            empty_slips = other_slips.filtered(lambda s: not s.attendance_gross_overtime and not s.attendance_gross_undertime)
            if empty_slips:
                empty_slips.attendance_gross_overtime = 0.0
                empty_slips.rest_days_taken = 0.0
                empty_slips.attendance_gross_undertime = 0.0
                empty_slips.attendance_net_reconciled = 0.0
                empty_slips.total_extra_hours_available = 0.0
                empty_slips.lateness_covered_by_extra_hours = 0.0
                empty_slips.lateness_covered_by_annual_leave = 0.0
                empty_slips.remaining_extra_hours_balance = 0.0
                empty_slips.undertime_cash_deduction_hours = 0.0

        if not valid_slips:
            return

        emp_ids = valid_slips.mapped('employee_id').ids
        min_date = min(valid_slips.mapped('date_from'))
        max_date = max(valid_slips.mapped('date_to'))

        public_holiday_dates = self.env['hr.attendance']._get_public_holiday_dates_batch(min_date, max_date)

        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', emp_ids),
            ('check_in', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
            ('check_in', '<=', datetime.datetime.combine(max_date, datetime.time.max))
        ])
        att_by_emp = defaultdict(list)
        for att in attendances:
            att_by_emp[att.employee_id.id].append(att)

        approved_ot_by_emp_date = defaultdict(float)
        banked_extra_by_emp = defaultdict(float)
        if 'hr.attendance.overtime.line' in self.env:
            ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('compensable_as_leave', '=', True),
                ('status', '=', 'approved'),
            ])
            for line in ot_lines:
                if line.date < min_date:
                    banked_extra_by_emp[line.employee_id.id] += line.duration
                elif min_date <= line.date <= max_date:
                    dur = line.manual_duration if hasattr(line, 'manual_duration') and line.manual_duration else line.duration
                    if dur > 0:
                        approved_ot_by_emp_date[(line.employee_id.id, line.date)] = dur

        LeaveType = self.env['hr.leave.type'].sudo()
        extra_types = LeaveType.search(['|', '|', ('name', '=', 'Extra Hours'), ('name', 'ilike', 'Extra Hours'), ('name', 'ilike', 'إضافي')])
        annual_types = LeaveType.search(['|', '|', ('name', '=', 'Annual Leave'), ('name', 'ilike', 'Annual Leave'), ('name', 'ilike', 'سنوي')])
        pto_types = LeaveType.search(['|', '|', ('name', '=', 'Paid Time Off'), ('name', 'ilike', 'Paid Time Off'), ('name', 'ilike', 'مدفوع')])

        extra_type_ids = set(extra_types.ids)
        annual_type_ids = set(annual_types.ids)
        pto_type_ids = set(pto_types.ids)
        target_type_ids = list(extra_type_ids | annual_type_ids | pto_type_ids)

        alloc_hours_by_emp_type = defaultdict(float)
        recon_alloc_hours_by_emp_name = {}
        if target_type_ids:
            allocations = self.env['hr.leave.allocation'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('state', '=', 'validate'),
                ('holiday_status_id', 'in', target_type_ids)
            ])
            for alloc in allocations:
                hrs = 0.0
                if hasattr(alloc, 'number_of_days') and alloc.number_of_days:
                    hrs = alloc.number_of_days * 8.0
                elif hasattr(alloc, 'number_of_days_display') and alloc.number_of_days_display:
                    hrs = alloc.number_of_days_display * 8.0
                elif hasattr(alloc, 'number_of_hours_display') and alloc.number_of_hours_display:
                    hrs = alloc.number_of_hours_display
                elif hasattr(alloc, 'number_of_hours') and alloc.number_of_hours:
                    hrs = alloc.number_of_hours
                alloc_hours_by_emp_type[(alloc.employee_id.id, alloc.holiday_status_id.id)] += hrs
                if 'Extra Hours Reconciliation' in (alloc.name or '') or 'Monthly Overtime Earned' in (alloc.name or ''):
                    recon_alloc_hours_by_emp_name[(alloc.employee_id.id, alloc.name or '')] = hrs

            taken_leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('state', '=', 'validate'),
                ('holiday_status_id', 'in', target_type_ids),
            ])
            for lve in taken_leaves:
                hrs = 0.0
                if hasattr(lve, 'number_of_days') and lve.number_of_days:
                    hrs = lve.number_of_days * 8.0
                elif hasattr(lve, 'number_of_days_display') and lve.number_of_days_display:
                    hrs = lve.number_of_days_display * 8.0
                elif hasattr(lve, 'number_of_hours') and lve.number_of_hours:
                    hrs = lve.number_of_hours
                elif hasattr(lve, 'number_of_hours_display') and lve.number_of_hours_display:
                    hrs = lve.number_of_hours_display
                alloc_hours_by_emp_type[(lve.employee_id.id, lve.holiday_status_id.id)] -= hrs

        leave_dates_by_emp = defaultdict(set)
        if 'hr.leave' in self.env:
            all_leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('state', 'in', ['validate', 'validate1']),
                ('date_from', '<=', datetime.datetime.combine(max_date, datetime.time.max)),
                ('date_to', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
                '!', ('name', 'ilike', 'Lateness Settlement')
            ])
            for lve in all_leaves:
                d_curr = lve.date_from.date()
                d_last = lve.date_to.date()
                while d_curr <= d_last:
                    if min_date <= d_curr <= max_date:
                        leave_dates_by_emp[lve.employee_id.id].add(d_curr)
                    d_curr += datetime.timedelta(days=1)

        monthly_rest_allowance = 4

        for payslip in valid_slips:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                payslip.attendance_gross_overtime = 0.0
                payslip.rest_days_taken = 0.0
                payslip.attendance_gross_undertime = 0.0
                payslip.attendance_net_reconciled = 0.0
                payslip.total_extra_hours_available = 0.0
                payslip.lateness_covered_by_extra_hours = 0.0
                payslip.lateness_covered_by_annual_leave = 0.0
                payslip.remaining_extra_hours_balance = 0.0
                payslip.undertime_cash_deduction_hours = 0.0
                continue

            if payslip.employee_id.is_manager_exempt():
                payslip.attendance_gross_overtime = 0.0
                payslip.rest_days_taken = 0.0
                payslip.attendance_gross_undertime = 0.0
                payslip.attendance_net_reconciled = 0.0
                payslip.total_extra_hours_available = 0.0
                payslip.lateness_covered_by_extra_hours = 0.0
                payslip.lateness_covered_by_annual_leave = 0.0
                payslip.remaining_extra_hours_balance = 0.0
                payslip.undertime_cash_deduction_hours = 0.0
                continue

            emp_id = payslip.employee_id.id
            emp_attendances = [
                att for att in att_by_emp.get(emp_id, [])
                if payslip.date_from <= att.check_in.date() <= payslip.date_to
            ]

            daily_hours = defaultdict(float)
            for att in emp_attendances:
                daily_hours[att.check_in.date()] += att.worked_hours

            company = payslip.company_id or self.env.company
            allow_ot = getattr(company, 'enable_overtime_calculation', True)
            break_hrs = payslip.employee_id._get_lunch_break_duration() if payslip.employee_id else 1.0
            min_ot_threshold = 0.75
            min_lateness_threshold = 0.25

            total_ot = 0.0
            total_undertime = 0.0

            if allow_ot:
                for att_date in set(att.check_in.date() for att in emp_attendances if att.check_in):
                    matching_atts = [a for a in emp_attendances if a.check_in and a.check_in.date() == att_date]
                    is_holiday = att_date in public_holiday_dates or any(getattr(a, 'is_public_holiday', False) for a in matching_atts)
                    is_approved = (
                        approved_ot_by_emp_date.get((emp_id, att_date), 0.0) > 0 or
                        any(getattr(a, 'overtime_status', False) == 'approved' or getattr(a, 'validated_overtime_hours', 0.0) > 0 for a in matching_atts)
                    )

                    if not is_approved:
                        continue

                    if is_holiday:
                        net_hol_hrs = sum(getattr(a, 'net_worked_hours', 0.0) or a.worked_hours for a in matching_atts)
                        if net_hol_hrs > 0:
                            total_ot += (net_hol_hrs * 1.5)
                    else:
                        app_ot_line = approved_ot_by_emp_date.get((emp_id, att_date), 0.0)
                        if app_ot_line > 0:
                            total_ot += (app_ot_line * 1.25)
                        else:
                            day_ot = sum(
                                getattr(a, 'validated_overtime_hours', 0.0) or getattr(a, 'daily_overtime_hours', 0.0)
                                for a in matching_atts
                                if getattr(a, 'overtime_status', False) == 'approved' or getattr(a, 'validated_overtime_hours', 0.0) > 0 or getattr(a, 'daily_overtime_hours', 0.0) >= min_ot_threshold
                            )
                            if day_ot >= min_ot_threshold:
                                total_ot += (day_ot * 1.25)

            # Sum official schedule-aware & break-aware daily undertime directly from Attendance records
            daily_punch_lateness = sum(
                att.daily_undertime_hours for att in emp_attendances
                if not getattr(att, 'is_public_holiday', False) and hasattr(att, 'daily_undertime_hours') and att.daily_undertime_hours
            )
            total_undertime += daily_punch_lateness

            # Bound calculation to active contract overlapping dates within payslip period
            contract_versions = payslip.employee_id._get_versions_with_contract_overlap_with_period(payslip.date_from, payslip.date_to)
            c_starts = [c.date_start for c in contract_versions if c.date_start]
            c_ends = [c.date_end for c in contract_versions if c.date_end]
            eff_date_from = max(payslip.date_from, min(c_starts)) if c_starts else payslip.date_from
            eff_date_to = min(payslip.date_to, max(c_ends)) if (c_ends and len(c_ends) == len(contract_versions)) else payslip.date_to

            active_contract_days = (eff_date_to - eff_date_from).days + 1 if eff_date_from <= eff_date_to else 0
            total_days_in_month = (payslip.date_to - payslip.date_from).days + 1
            target_work_days = active_contract_days - (active_contract_days // 7)
            regular_worked_days_count = sum(1 for d in daily_hours.keys() if d not in public_holiday_dates)
            is_termination = getattr(payslip, 'termination_clearance', False)
            is_partial_period = is_termination or active_contract_days < 25

            if not is_partial_period and active_contract_days > 0:
                if regular_worked_days_count > target_work_days:
                    if allow_ot:
                        extra_worked_days = regular_worked_days_count - target_work_days
                        approved_extra_days = sum(1 for d in daily_hours.keys() if approved_ot_by_emp_date.get((emp_id, d), 0) > 0)
                        eff_extra_days = min(extra_worked_days, approved_extra_days) if approved_extra_days else 0
                        if eff_extra_days > 0:
                            total_ot += (eff_extra_days * 8.0 * 1.25)

            # Combine daily punch lateness with full unworked ABSENT days (e.g. 14:35 punch lateness + 8:00 absent = 22:35)
            WEModel = self.env['hr.work.entry']
            if 'hr.work.entry' in self.env:
                we_domain = [
                    ('employee_id', '=', emp_id),
                    ('state', '!=', 'cancelled'),
                    '|', ('work_entry_type_id.code', 'in', ['ABSENT', 'ABS']),
                    ('work_entry_type_id.display_code', 'in', ['ABSENT', 'ABS']),
                ]
                if 'date' in WEModel._fields:
                    we_domain += [('date', '>=', eff_date_from), ('date', '<=', eff_date_to)]
                elif 'date_start' in WEModel._fields:
                    we_domain += [
                        ('date_start', '>=', datetime.datetime.combine(eff_date_from, datetime.time.min)),
                        ('date_start', '<=', datetime.datetime.combine(eff_date_to, datetime.time.max)),
                    ]
                absent_entries = WEModel.sudo().search(we_domain)
                for we in absent_entries:
                    dur = getattr(we, 'duration', 8.0) or 8.0
                    total_undertime += dur

            # Weekly rest/off days: monthly allowance 4; unused × 8 × 1.5 → Monthly OT
            worked_days_count = len(daily_hours)
            emp_leave_dates = leave_dates_by_emp.get(emp_id, set())
            approved_leave_days_count = sum(
                1 for d in range(total_days_in_month)
                if (payslip.date_from + datetime.timedelta(days=d)) not in daily_hours
                and ((payslip.date_from + datetime.timedelta(days=d)) in emp_leave_dates or
                     (payslip.date_from + datetime.timedelta(days=d)) in public_holiday_dates)
            )
            rest_days_taken = max(0, total_days_in_month - worked_days_count - approved_leave_days_count)
            unused_rest_days = max(0, monthly_rest_allowance - rest_days_taken)
            if allow_ot and unused_rest_days > 0:
                total_ot += (unused_rest_days * 8.0 * 1.5)

            gross_ot = round(total_ot, 2)
            gross_ut = round(total_undertime, 2)

            payslip.attendance_gross_overtime = gross_ot
            payslip.rest_days_taken = float(rest_days_taken)
            payslip.attendance_gross_undertime = gross_ut
            payslip.attendance_net_reconciled = round(gross_ot - gross_ut, 2)

            current_slip_allocated_hours = (payslip.extra_hours_allocated_days or 0.0) * 8.0
            month_str = payslip.date_to.strftime('%B %Y') if payslip.date_to else ''
            current_recon_name = f"Extra Hours Reconciliation: {month_str} - {payslip.employee_id.name}"
            current_recon_hours = recon_alloc_hours_by_emp_name.get((emp_id, current_recon_name), 0.0)
            exclude_current_hrs = max(current_slip_allocated_hours, current_recon_hours)
            prior_alloc_extra = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in extra_type_ids) - exclude_current_hrs)
            prior_ot_line_extra = round(banked_extra_by_emp.get(emp_id, 0.0), 2)
            prev_extra_hours = max(prior_alloc_extra, prior_ot_line_extra)

            total_extra_avail = round(prev_extra_hours + gross_ot, 2)
            payslip.total_extra_hours_available = total_extra_avail

            lateness = gross_ut
            covered_extra = round(min(lateness, total_extra_avail), 2)
            rem_lateness = round(lateness - covered_extra, 2)

            covered_annual_leave = 0.0
            if rem_lateness > 0.01 and payslip.employee_id and payslip.employee_id.allow_annual_leave_lateness_deduction:
                annual_leave_avail = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in annual_type_ids))
                covered_annual_leave = round(min(rem_lateness, annual_leave_avail), 2)
                rem_lateness = round(rem_lateness - covered_annual_leave, 2)

            if rem_lateness < 0.01:
                rem_lateness = 0.0

            payslip.lateness_covered_by_extra_hours = covered_extra
            payslip.remaining_extra_hours_balance = round(max(0.0, total_extra_avail - covered_extra), 2)
            payslip.lateness_covered_by_annual_leave = covered_annual_leave
            payslip.undertime_cash_deduction_hours = rem_lateness

    def compute_sheet(self):
        valid_slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to)
        if valid_slips:
            valid_slips._compute_attendance_reconciliation_fields()
            valid_slips._apply_termination_clearance_inputs()
            valid_slips._normalize_public_holiday_work_entries()

        self._convert_flexible_rest_days_to_ars()

        res = super().compute_sheet()
        self.write({'is_reconciled': True})
        return res

    def _normalize_public_holiday_work_entries(self):
        valid_slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to)
        if not valid_slips or 'hr.work.entry' not in self.env:
            return

        emp_ids = valid_slips.mapped('employee_id').ids
        min_date = min(valid_slips.mapped('date_from'))
        max_date = max(valid_slips.mapped('date_to'))

        WEModel = self.env['hr.work.entry']
        we_domain = [
            ('employee_id', 'in', emp_ids),
            ('state', '!=', 'cancelled'),
            '|', '|', ('work_entry_type_id.code', 'in', ['PHD', 'GTO', 'HOLIDAY', 'LEAVE110']),
            ('work_entry_type_id.display_code', 'in', ['PHD', 'GTO', 'HOLIDAY', 'LEAVE110']),
            ('work_entry_type_id.name', 'ilike', 'Public Holiday'),
        ]
        if 'date' in WEModel._fields:
            we_domain += [('date', '>=', min_date), ('date', '<=', max_date)]
        elif 'date_start' in WEModel._fields:
            we_domain += [
                ('date_start', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
                ('date_start', '<=', datetime.datetime.combine(max_date, datetime.time.max)),
            ]

        ph_entries = WEModel.sudo().search(we_domain)
        to_fix = ph_entries.filtered(lambda w: getattr(w, 'duration', 0.0) > 8.0)
        for we in to_fix:
            try:
                if hasattr(we, 'state') and we.state == 'validated':
                    we.sudo().write({'state': 'draft'})
                vals = {'duration': 8.0}
                if hasattr(we, 'date_start') and we.date_start and hasattr(we, 'date_stop'):
                    vals['date_stop'] = we.date_start + datetime.timedelta(hours=8.0)
                we.sudo().write(vals)
            except Exception:
                pass

    def _apply_termination_clearance_inputs(self):
        input_model = self.env["hr.payslip.input"]
        for slip in self:
            is_term = (
                getattr(slip, 'termination_clearance', False) or
                (slip.struct_id and ('termination' in slip.struct_id.name.lower() or 'تيرمنيشن' in slip.struct_id.name))
            )
            if not is_term or not slip.employee_id:
                continue

            emp = slip.employee_id
            w = emp.wage or 0.0
            hourly_rate = w / 240.0
            daily_rate = w / 30.0

            # 1. CLEAR_EXTRA (Termination: Extra Days / Overtime Settlement)
            ot_hrs = max(0.0, round(slip.remaining_extra_hours_balance, 2))
            ot_amount = round(ot_hrs * hourly_rate, 3)
            ot_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'CLEAR_EXTRA')], limit=1)
            if ot_type:
                ot_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == ot_type)
                if ot_line:
                    ot_line.write({'quantity': ot_hrs, 'amount': ot_amount})
                else:
                    if slip.id:
                        input_model.create({
                            'payslip_id': slip.id,
                            'input_type_id': ot_type.id,
                            'quantity': ot_hrs,
                            'amount': ot_amount,
                        })
                    else:
                        slip.input_line_ids += input_model.new({
                            'payslip_id': slip.id,
                            'input_type_id': ot_type.id,
                            'quantity': ot_hrs,
                            'amount': ot_amount,
                        })

            # Fetch Annual & PTO Leave Balances
            annual_leave_days = 0.0
            pto_leave_days = 0.0

            # ----------------------------------------------------
            # A. ANNUAL LEAVE BALANCES
            # ----------------------------------------------------
            annual_types = self.env['hr.leave.type'].sudo().search([
                '|', ('name', 'ilike', 'annual'), ('name', 'ilike', 'سنوي')
            ])
            for atype in annual_types:
                if hasattr(emp, '_get_consumed_leaves'):
                    try:
                        consumed_data, _ = emp._get_consumed_leaves(atype, target_date=slip.date_to or fields.Date.today())
                        leave_content = consumed_data.get(emp, {}).get(atype, {})
                        if isinstance(leave_content, dict):
                            val = leave_content.get('virtual_remaining_leaves') or leave_content.get('remaining_leaves') or 0.0
                            if not val:
                                val = sum(v.get('virtual_remaining_leaves', 0.0) for v in leave_content.values() if isinstance(v, dict))
                            if val:
                                annual_leave_days += float(val)
                    except Exception:
                        pass

            if not annual_leave_days:
                for field_name in ['annual_leave_balance', 'remaining_leaves', 'annual_leave_balance_hours']:
                    if field_name in emp._fields and getattr(emp, field_name):
                        val = getattr(emp, field_name)
                        annual_leave_days = val / 8.0 if 'hours' in field_name else val
                        break

            if not annual_leave_days and 'hr.leave.allocation' in self.env:
                annual_allocs = self.env['hr.leave.allocation'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'validate'),
                    '|', ('holiday_status_id.name', 'ilike', 'annual'),
                    ('holiday_status_id.name', 'ilike', 'سنوي'),
                ])
                if annual_allocs:
                    for a in annual_allocs:
                        rem = getattr(a, 'number_of_days_display', 0.0) or getattr(a, 'number_of_days', 0.0) or 0.0
                        taken = getattr(a, 'leaves_taken', 0.0) or 0.0
                        annual_leave_days += max(0.0, rem - taken)

            # ----------------------------------------------------
            # B. PAID TIME OFF (PTO) BALANCES
            # ----------------------------------------------------
            pto_types = self.env['hr.leave.type'].sudo().search([
                '|', '|', ('name', 'ilike', 'paid time off'), ('name', 'ilike', 'مدفوع'), ('name', 'ilike', 'pto')
            ])
            for ptype in pto_types:
                if hasattr(emp, '_get_consumed_leaves'):
                    try:
                        consumed_data_pto, _ = emp._get_consumed_leaves(ptype, target_date=slip.date_to or fields.Date.today())
                        leave_content_pto = consumed_data_pto.get(emp, {}).get(ptype, {})
                        if isinstance(leave_content_pto, dict):
                            val = leave_content_pto.get('virtual_remaining_leaves') or leave_content_pto.get('remaining_leaves') or 0.0
                            if not val:
                                val = sum(v.get('virtual_remaining_leaves', 0.0) for v in leave_content_pto.values() if isinstance(v, dict))
                            if val:
                                pto_leave_days += float(val)
                    except Exception:
                        pass

            if not pto_leave_days and 'hr.leave.allocation' in self.env:
                pto_allocs = self.env['hr.leave.allocation'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'validate'),
                    '|', '|', ('holiday_status_id.name', 'ilike', 'paid time off'),
                    ('holiday_status_id.name', 'ilike', 'مدفوع'),
                    ('holiday_status_id.name', 'ilike', 'pto')
                ])
                if pto_allocs:
                    for a in pto_allocs:
                        rem = getattr(a, 'number_of_days_display', 0.0) or getattr(a, 'number_of_days', 0.0) or 0.0
                        taken = getattr(a, 'leaves_taken', 0.0) or 0.0
                        pto_leave_days += max(0.0, rem - taken)

            # Deduct Step 2 lateness covered by annual leave (converted from hours to days) to reflect post-reconciliation balance
            lateness_annual_days = (slip.lateness_covered_by_annual_leave or 0.0) / 8.0
            post_recon_annual_leave_days = max(0.0, round(annual_leave_days - lateness_annual_days, 4))

            # 2. CLEAR_ANNUAL (Termination: Annual Leave Settlement)
            annual_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'CLEAR_ANNUAL')], limit=1)
            if annual_type:
                annual_amount = round(post_recon_annual_leave_days * daily_rate, 3)
                annual_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == annual_type)
                if annual_line:
                    annual_line.write({'quantity': post_recon_annual_leave_days, 'amount': annual_amount})
                else:
                    if slip.id:
                        input_model.create({
                            'payslip_id': slip.id,
                            'input_type_id': annual_type.id,
                            'quantity': post_recon_annual_leave_days,
                            'amount': annual_amount,
                        })
                    else:
                        slip.input_line_ids += input_model.new({
                            'payslip_id': slip.id,
                            'input_type_id': annual_type.id,
                            'quantity': post_recon_annual_leave_days,
                            'amount': annual_amount,
                        })

            # 3. CLEAR_PTO (Termination: Paid Time Off Settlement)
            pto_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'CLEAR_PTO')], limit=1)
            if pto_type:
                pto_amount = round(pto_leave_days * daily_rate, 3)
                pto_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == pto_type)
                if pto_line:
                    pto_line.write({'quantity': pto_leave_days, 'amount': pto_amount})
                else:
                    if slip.id:
                        input_model.create({
                            'payslip_id': slip.id,
                            'input_type_id': pto_type.id,
                            'quantity': pto_leave_days,
                            'amount': pto_amount,
                        })
                    else:
                        slip.input_line_ids += input_model.new({
                            'payslip_id': slip.id,
                            'input_type_id': pto_type.id,
                            'quantity': pto_leave_days,
                            'amount': pto_amount,
                        })

    @api.onchange('termination_clearance', 'employee_id', 'struct_id')
    def _onchange_termination_clearance(self):
        self._compute_attendance_reconciliation_fields()
        self._apply_termination_clearance_inputs()

    def action_payslip_done(self):
        _logger.info(
            "[FAP-RECON] action_payslip_done START slips=%s states=%s",
            self.ids,
            {s.id: s.state for s in self},
        )
        res = super().action_payslip_done()
        _logger.info(
            "[FAP-RECON] action_payslip_done AFTER super slips=%s states=%s → sync",
            self.ids,
            {s.id: s.state for s in self},
        )
        try:
            self.with_context(recon_synced_via_action=True)._sync_reconciliation_settlements()
        except Exception:
            _logger.exception("[FAP-RECON] action_payslip_done FAILED sync slips=%s", self.ids)
            raise
        _logger.info("[FAP-RECON] action_payslip_done DONE slips=%s", self.ids)
        return res

    def action_payslip_draft(self):
        _logger.info("[FAP-RECON] action_payslip_draft → revert slips=%s", self.ids)
        self._revert_reconciliation_settlements()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        _logger.info("[FAP-RECON] action_payslip_cancel → revert slips=%s", self.ids)
        self._revert_reconciliation_settlements()
        return super().action_payslip_cancel()

    def action_cancel(self):
        _logger.info("[FAP-RECON] action_cancel → revert slips=%s", self.ids)
        self._revert_reconciliation_settlements()
        return super().action_cancel() if hasattr(super(), 'action_cancel') else True

    def unlink(self):
        _logger.info("[FAP-RECON] unlink → revert slips=%s", self.ids)
        self._revert_reconciliation_settlements()
        return super().unlink()

    def write(self, vals):
        if vals.get('state') == 'cancel' and not self._context.get('skip_reconcile_revert'):
            _logger.info("[FAP-RECON] write(state=cancel) → revert slips=%s", self.ids)
            self.with_context(skip_reconcile_revert=True)._revert_reconciliation_settlements()
        going_done = vals.get('state') == 'done' and not self._context.get('skip_recon_sync')
        already_done_ids = set(self.filtered(lambda s: s.state == 'done').ids) if going_done else set()
        res = super().write(vals)
        if going_done:
            to_sync = self.filtered(lambda s: s.state == 'done' and s.id not in already_done_ids)
            if to_sync and not self.env.context.get('recon_synced_via_action'):
                _logger.info("[FAP-RECON] write(state=done) backup sync slips=%s", to_sync.ids)
                try:
                    to_sync.with_context(recon_synced_via_action=True)._sync_reconciliation_settlements()
                except Exception:
                    _logger.exception("[FAP-RECON] write(state=done) backup sync FAILED slips=%s", to_sync.ids)
                    raise
        return res

    def _round_days(self, work_entry_type, days):
        round_days = work_entry_type.round_days or 'NO'
        if round_days == 'NO':
            return days
        rounding_method = work_entry_type.round_days_type or 'DOWN'
        precision_rounding = 0.5 if round_days == 'HALF' else 1
        rounded = float_round(
            days,
            precision_rounding=precision_rounding,
            rounding_method=rounding_method,
        )
        return rounded

    def _get_fixed_schedule_rest_days(self, emp, start_date, end_date):
        if not emp or not emp.resource_calendar_id or not start_date or not end_date:
            return 0
        cal = emp.resource_calendar_id
        working_days_of_week = set(int(att.dayofweek) for att in cal.attendance_ids if att.dayofweek is not False and att.dayofweek is not None)
        rest_count = 0
        curr = start_date
        while curr <= end_date:
            if curr.weekday() not in working_days_of_week:
                rest_count += 1
            curr += datetime.timedelta(days=1)
        return rest_count

    def _get_worked_day_lines(self, *args, **kwargs):
        res = super()._get_worked_day_lines(*args, **kwargs)
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue

            emp = payslip.employee_id
            break_hrs = emp._get_lunch_break_duration() if emp else 1.0
            w = emp.wage if emp else 0.0

            attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', emp.id),
                ('check_in', '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                ('check_in', '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max))
            ])

            cal_id = emp.resource_calendar_id.id if emp and emp.resource_calendar_id else False
            holiday_dates = self.env['hr.attendance']._get_public_holiday_dates_batch(payslip.date_from, payslip.date_to, calendar_id=cal_id)
            regular_attendances = attendances.filtered(lambda a: a.check_in.date() not in holiday_dates)
            holiday_attendances = attendances.filtered(lambda a: a.check_in.date() in holiday_dates)

            def _net_hrs(att):
                if hasattr(att, 'net_worked_hours') and att.net_worked_hours:
                    return att.net_worked_hours
                raw = (att.check_out - att.check_in).total_seconds() / 3600.0 if (att.check_in and att.check_out) else (att.worked_hours or 0.0)
                if raw >= 6.0:
                    return max(0.0, raw - break_hrs)
                elif raw > 4.0:
                    return max(0.0, raw - (break_hrs / 2.0))
                return raw

            total_regular_attendance_hrs = round(sum(_net_hrs(att) for att in regular_attendances), 2)
            total_holiday_worked_hrs = round(sum(_net_hrs(att) for att in holiday_attendances), 2)

            rem_cash_deduction_hrs = round(payslip.undertime_cash_deduction_hours, 2)
            total_scheduled_hours = total_regular_attendance_hrs + total_holiday_worked_hrs + rem_cash_deduction_hrs
            if total_scheduled_hours > 0:
                hourly_rate = w / total_scheduled_hours
            else:
                weekly_hours = (emp.resource_calendar_id.full_time_required_hours if emp.resource_calendar_id else None) or 49.5
                hourly_rate = (w / 26.0) / (weekly_hours / 6.0)
            hourly_rate = round(hourly_rate, 4)

            company = payslip.company_id or self.env.company
            allow_ot = getattr(company, 'enable_overtime_calculation', True)
            net_extra_hrs = round(payslip.attendance_gross_overtime - payslip.lateness_covered_by_extra_hours, 2) if allow_ot else 0.0

            filtered_lines = []
            for line in res:
                code = (line.get('code') or '').strip()
                work_entry_type = self.env['hr.work.entry.type'].browse(line.get('work_entry_type_id')) if line.get('work_entry_type_id') else None
                we_name = (work_entry_type.name or '').lower() if work_entry_type else ''
                line_name = (line.get('name') or '').lower()

                if 'settlement' in line_name or 'lateness coverage' in line_name or 'monthly lateness' in line_name:
                    continue

                if code in ['ARS', 'REST', 'RESTDAY'] or 'rest' in we_name or 'rest day' in line_name or 'restday' in line_name:
                    continue

                if code in ['WORK100', 'A', 'ATTENDANCE'] or 'attendance' in we_name:
                    if total_regular_attendance_hrs > 0.01:
                        line['number_of_hours'] = total_regular_attendance_hrs
                        
                        if regular_attendances:
                            regular_physical_days = len(set(att.check_in.date() for att in regular_attendances if att.check_in))
                        else:
                            regular_physical_days = round(total_regular_attendance_hrs / 8.0, 2)

                        if attendances:
                            total_physical_days = len(set(att.check_in.date() for att in attendances if att.check_in))
                        else:
                            total_physical_days = regular_physical_days

                        is_flexible = getattr(emp.resource_calendar_id, 'flexible_hours', False) or getattr(emp, 'flexible_hours', False)
                        if is_flexible:
                            contract_obj = getattr(payslip, 'contract_id', None) or getattr(payslip, 'version_id', None) or getattr(emp, 'contract_id', None)
                            c_start = getattr(contract_obj, 'date_start', None) if contract_obj else None
                            if c_start and c_start > payslip.date_from:
                                active_m_from = max(payslip.date_from, c_start)
                                earned_rest_days = sum(
                                    1 for d_idx in range((payslip.date_to - active_m_from).days + 1)
                                    if (active_m_from + datetime.timedelta(days=d_idx)).weekday() == 0
                                )
                            else:
                                earned_rest_days = int(total_physical_days // 6)
                        else:
                            c_start = payslip.date_from
                            c_end = payslip.date_to
                            
                            contract_obj = getattr(payslip, 'contract_id', None) or getattr(payslip, 'version_id', None) or getattr(emp, 'contract_id', None)
                            if contract_obj and getattr(contract_obj, 'date_start', None) and contract_obj.date_start > payslip.date_from:
                                c_start = contract_obj.date_start
                            elif hasattr(emp, '_get_versions_with_contract_overlap_with_period'):
                                c_vers = emp._get_versions_with_contract_overlap_with_period(payslip.date_from, payslip.date_to)
                                c_starts = [c.date_start for c in c_vers if getattr(c, 'date_start', None)]
                                if c_starts and max(c_starts) > payslip.date_from:
                                    c_start = max(c_starts)

                            if contract_obj and getattr(contract_obj, 'date_end', None) and contract_obj.date_end < payslip.date_to:
                                c_end = contract_obj.date_end

                            earned_rest_days = payslip._get_fixed_schedule_rest_days(emp, c_start, c_end)

                        line['number_of_days'] = float(regular_physical_days + earned_rest_days)
                        line['amount'] = round(total_regular_attendance_hrs * hourly_rate, 3)
                        filtered_lines.append(line)

                elif code in ['GTO', 'PHD', 'HOLIDAY', 'LEAVE110', 'PHW', 'HOLIDAY_WORKED'] or 'public holiday' in we_name or 'holiday' in we_name:
                    if total_holiday_worked_hrs > 0.01:
                        weighted_hol_hrs = round(total_holiday_worked_hrs * 1.5, 2)
                        line['number_of_hours'] = weighted_hol_hrs
                        line['number_of_days'] = float(len(set(att.check_in.date() for att in holiday_attendances))) if holiday_attendances else round(weighted_hol_hrs / 8.0, 2)
                        line['amount'] = round(weighted_hol_hrs * hourly_rate, 3)
                    else:
                        actual_hol_days = len(holiday_dates) if holiday_dates else 1.0
                        base_hrs = round(actual_hol_days * 8.0, 2)
                        line['number_of_hours'] = base_hrs
                        line['number_of_days'] = round(actual_hol_days, 2)
                        line['amount'] = 0.0
                    filtered_lines.append(line)

                elif code in ['OVERTIME', 'EXTRA', 'OUT'] or 'overtime' in we_name or 'extra' in we_name:
                    if net_extra_hrs > 0.01:
                        line['number_of_hours'] = net_extra_hrs
                        line['number_of_days'] = round(net_extra_hrs / 8.0, 2)
                        line['amount'] = round(net_extra_hrs * hourly_rate, 3)
                        filtered_lines.append(line)

                elif code in ['LEAVE500', 'UNPAID', 'ABSENT', 'ABS'] or 'absent' in we_name:
                    if rem_cash_deduction_hrs > 0.01:
                        line['number_of_hours'] = rem_cash_deduction_hrs
                        line['number_of_days'] = round(rem_cash_deduction_hrs / 8.0, 2)
                        line['amount'] = round(rem_cash_deduction_hrs * hourly_rate, 3)
                        filtered_lines.append(line)
                else:
                    filtered_lines.append(line)

            res = filtered_lines
        return res

    def _convert_flexible_rest_days_to_ars(self):
        valid_slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to)
        if not valid_slips or 'hr.work.entry' not in self.env:
            return

        rest_type = self.env['hr.work.entry.type'].sudo().search([
            '|', ('code', '=', 'ARS'), ('name', 'ilike', 'Rest')
        ], limit=1)
        if not rest_type:
            return

        emp_ids = valid_slips.mapped('employee_id').ids
        min_date = min(valid_slips.mapped('date_from'))
        max_date = max(valid_slips.mapped('date_to'))

        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', emp_ids),
            ('check_in', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
            ('check_in', '<=', datetime.datetime.combine(max_date, datetime.time.max))
        ])
        worked_dates_by_emp = defaultdict(set)
        for att in attendances:
            worked_dates_by_emp[att.employee_id.id].add(att.check_in.date())

        we_domain = [('employee_id', 'in', emp_ids)]
        WEModel = self.env['hr.work.entry']
        if 'date' in WEModel._fields:
            we_domain += [('date', '>=', min_date), ('date', '<=', max_date)]
        elif 'date_start' in WEModel._fields:
            we_domain += [
                ('date_start', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
                ('date_start', '<=', datetime.datetime.combine(max_date, datetime.time.max))
            ]
        work_entries = WEModel.sudo().search(we_domain)
        we_by_emp = defaultdict(list)
        for we in work_entries:
            we_by_emp[we.employee_id.id].append(we)

        to_update = self.env['hr.work.entry']
        for payslip in valid_slips:
            try:
                emp = payslip.employee_id
                is_flexible = getattr(emp.resource_calendar_id, 'flexible_hours', False) or getattr(emp, 'flexible_hours', False)
                if not is_flexible:
                    continue
                emp_id = emp.id
                emp_work_entries = we_by_emp.get(emp_id, [])
                slip_worked_dates = set(
                    d for d in worked_dates_by_emp.get(emp_id, set())
                    if payslip.date_from <= d <= payslip.date_to
                )
                physical_attendance_days = len(slip_worked_dates)
                contract_obj = getattr(payslip, 'contract_id', None) or getattr(payslip, 'version_id', None) or getattr(emp, 'contract_id', None)
                c_start = getattr(contract_obj, 'date_start', None) if contract_obj else None
                if c_start and c_start > payslip.date_from:
                    active_m_from = max(payslip.date_from, c_start)
                    allowed_rest_days = sum(
                        1 for d_idx in range((payslip.date_to - active_m_from).days + 1)
                        if (active_m_from + datetime.timedelta(days=d_idx)).weekday() == 0
                    )
                else:
                    allowed_rest_days = physical_attendance_days // 6
                converted_count = 0
                for we in emp_work_entries:
                    code = (we.work_entry_type_id.code or '').strip().upper()
                    name = (we.work_entry_type_id.name or '').lower()
                    if code in ['LEAVE500', 'UNPAID', 'UNP', 'ABSENT', 'ABS'] or 'absent' in name:
                        if converted_count < allowed_rest_days:
                            to_update |= we
                            converted_count += 1
            except Exception as e:
                _logger.error("Error in _convert_flexible_rest_days_to_ars for payslip %s: %s", payslip.id, e)

        if to_update:
            draft_we = to_update.filtered(lambda w: hasattr(w, 'state') and w.state == 'validated')
            if draft_we:
                draft_we.sudo().write({'state': 'draft'})
            to_update.sudo().write({'work_entry_type_id': rest_type.id})

    def _create_or_update_settlement_leave(self, leave_type_name, hours, leave_desc):
        self.ensure_one()
        if hours <= 0.01 or 'hr.leave' not in self.env:
            return

        Leave = self.env['hr.leave'].sudo()
        LeaveType = self.env['hr.leave.type'].sudo()
        company = self.company_id or self.env.company
        comp_domain = [('company_id', 'in', [False, company.id])]

        if leave_type_name == 'Extra Hours':
            leave_types = LeaveType.search(comp_domain + ['|', '|', ('name', '=', 'Extra Hours'), ('name', 'ilike', 'Extra Hours'), ('name', 'ilike', 'إضافي')])
        elif leave_type_name == 'Annual Leave':
            leave_types = LeaveType.search(comp_domain + ['|', '|', ('name', '=', 'Annual Leave'), ('name', 'ilike', 'Annual Leave'), ('name', 'ilike', 'سنوي')])
        else:
            leave_types = LeaveType.search(comp_domain + [('name', '=', leave_type_name)])

        leave_type = leave_types[0] if leave_types else None
        if not leave_type:
            return

        prev_settlement_leaves = Leave.search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', leave_type.id),
            ('request_date_from', '>=', self.date_from),
            ('request_date_to', '<=', self.date_to),
            ('name', 'ilike', 'Lateness Settlement'),
        ])
        if prev_settlement_leaves:
            prev_settlement_leaves.unlink()

        alloc = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
        ], order='date_to desc, id desc', limit=1)

        ctx_leave = Leave.with_context(
            employee_id=self.employee_id.id,
            mail_create_nolog=True,
            mail_notrack=True,
            tracking_disable=True,
            leave_skip_state_check=True,
            leave_skip_work_entries=True,
            no_work_entry=True,
            leave_skip_payslip_check=True,
            leave_skip_date_check=True,
            skip_payslip_validation=True,
            payslip_skip_leave_check=True,
            leave_fast_create=True,
        )

        remaining_hours = hours
        curr_d = self.date_from
        while curr_d <= self.date_to and remaining_hours >= 7.99:
            dt_start = datetime.datetime.combine(curr_d, datetime.time(8, 0, 0))
            dt_stop = datetime.datetime.combine(curr_d, datetime.time(17, 0, 0))
            full_name = f"Lateness Settlement ({leave_type_name}) - {curr_d.strftime('%d/%m/%Y')}"
            vals = {
                'name': full_name,
                'employee_id': self.employee_id.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': curr_d,
                'request_date_to': curr_d,
                'date_from': dt_start,
                'date_to': dt_stop,
                'number_of_days': 1.0,
                'state': 'validate',
            }
            if alloc and 'holiday_allocation_id' in Leave._fields:
                vals['holiday_allocation_id'] = alloc.id
            try:
                new_lve = ctx_leave.create(vals)
                new_lve.sudo().write({'state': 'validate'})
            except Exception:
                pass
            remaining_hours -= 8.0
            curr_d += datetime.timedelta(days=1)

        if remaining_hours > 0.01 and curr_d <= self.date_to:
            frac_hours = round(remaining_hours, 2)
            frac_days = round(frac_hours / 8.0, 4)
            dt_start = datetime.datetime.combine(curr_d, datetime.time(8, 0, 0))
            dt_stop = dt_start + datetime.timedelta(hours=frac_hours)
            full_name = f"Lateness Settlement ({leave_type_name}) - {frac_hours}h ({curr_d.strftime('%d/%m/%Y')})"
            vals = {
                'name': full_name,
                'employee_id': self.employee_id.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': curr_d,
                'request_date_to': curr_d,
                'date_from': dt_start,
                'date_to': dt_stop,
                'number_of_days': frac_days,
                'state': 'validate',
            }
            if alloc and 'holiday_allocation_id' in Leave._fields:
                vals['holiday_allocation_id'] = alloc.id
            try:
                new_lve = ctx_leave.create(vals)
                new_lve.sudo().write({'state': 'validate'})
            except Exception:
                pass

    def _sync_reconciliation_settlements(self):
        _logger.info(
            "[FAP-RECON] _sync_reconciliation_settlements START slips=%s",
            self.ids,
        )
        has_leave_type = 'hr.leave.type' in self.env
        has_allocation = 'hr.leave.allocation' in self.env
        LeaveType = self.env['hr.leave.type'].sudo() if has_leave_type else None
        Allocation = self.env['hr.leave.allocation'].sudo() if has_allocation else None
        _logger.info(
            "[FAP-RECON] has_leave_type=%s has_allocation=%s",
            has_leave_type,
            has_allocation,
        )

        for payslip in self:
            try:
                _logger.info(
                    "[FAP-RECON] slip=%s emp=%s(%s) period=%s→%s state=%s "
                    "gross_ot=%s rest_days_taken=%s lateness=%s covered_extra=%s "
                    "total_extra_avail=%s remaining_extra=%s allocated_days=%s",
                    payslip.id,
                    payslip.employee_id.id,
                    payslip.employee_id.name,
                    payslip.date_from,
                    payslip.date_to,
                    payslip.state,
                    payslip.attendance_gross_overtime,
                    getattr(payslip, 'rest_days_taken', None),
                    payslip.attendance_gross_undertime,
                    payslip.lateness_covered_by_extra_hours,
                    payslip.total_extra_hours_available,
                    payslip.remaining_extra_hours_balance,
                    payslip.extra_hours_allocated_days,
                )
                if not payslip.employee_id or not payslip.date_to:
                    _logger.warning("[FAP-RECON] slip=%s SKIP: missing employee or date_to", payslip.id)
                    continue

                month_str = payslip.date_to.strftime('%B %Y') if payslip.date_to else ''

                # 1) Annual Leave lateness settlement only.
                # Extra Hours Step 1 is applied by forcing Time Off balance to Remaining
                # (Remaining already has Step 1 deducted). Creating an Extra Hours lateness
                # leave + force caused FIFO consumption on the newest allocation.
                _logger.info(
                    "[FAP-RECON] slip=%s settlements extra=%s (skipped leave; force handles) annual=%s",
                    payslip.id,
                    payslip.lateness_covered_by_extra_hours,
                    payslip.lateness_covered_by_annual_leave,
                )
                payslip._create_or_update_settlement_leave(
                    'Annual Leave', payslip.lateness_covered_by_annual_leave, 'Annual Leave Settlement'
                )

                # 2) Force Time Off Extra Hours available == Remaining Extra Hours Balance
                if has_allocation and has_leave_type and Allocation is not None and LeaveType is not None:
                    extra_types = LeaveType.search([
                        '|', '|',
                        ('name', '=', 'Extra Hours'),
                        ('name', 'ilike', 'Extra Hours'),
                        ('name', 'ilike', 'إضافي'),
                    ])
                    extra_type = extra_types[0] if extra_types else None
                    if not extra_type:
                        _logger.error("[FAP-RECON] slip=%s NO Extra Hours leave type", payslip.id)
                    else:
                        alloc_name = f"Extra Hours Reconciliation: {month_str} - {payslip.employee_id.name}"
                        payslip._fap_force_extra_hours_to_remaining(extra_type, alloc_name)
                else:
                    _logger.error(
                        "[FAP-RECON] slip=%s Allocation/LeaveType model missing — skip force sync",
                        payslip.id,
                    )

                # Optional: sync remaining hours onto employee profile float fields if present
                emp = payslip.employee_id
                updated_ot_balance = round(payslip.remaining_extra_hours_balance or 0.0, 2)
                for field_name in ['total_overtime', 'total_extra_hours', 'extra_hours_balance', 'overtime_balance']:
                    if field_name in emp._fields:
                        try:
                            emp.sudo().write({field_name: updated_ot_balance})
                        except Exception as e:
                            _logger.warning(
                                "[FAP-RECON] Could not sync %s to employee %s: %s",
                                field_name, emp.id, e,
                            )
                _logger.info("[FAP-RECON] slip=%s settlements + force sync done", payslip.id)
            except Exception:
                _logger.exception("[FAP-RECON] slip=%s FAILED in sync loop", payslip.id)
                raise

        _logger.info("[FAP-RECON] _sync_reconciliation_settlements END slips=%s", self.ids)

    def _fap_log_extra_hours_snapshot(self, extra_type, label='SNAPSHOT'):
        """Dump Extra Hours allocations + leaves so we can see why UI differs from FORCE calc."""
        self.ensure_one()
        emp = self.employee_id
        if not emp or not extra_type:
            _logger.info("[FAP-RECON] slip=%s %s skipped (no emp/type)", self.id, label)
            return 0.0

        Allocation = self.env['hr.leave.allocation'].sudo()
        Leave = self.env['hr.leave'].sudo() if 'hr.leave' in self.env else None

        hours_per_day = 8.0
        try:
            if hasattr(emp, '_get_hours_per_day'):
                hours_per_day = emp._get_hours_per_day(self.date_to or fields.Date.context_today(self)) or 8.0
        except Exception as e:
            _logger.info("[FAP-RECON] slip=%s %s hours_per_day fallback 8.0 err=%s", self.id, label, e)
            hours_per_day = 8.0

        leave_type_unit = getattr(extra_type, 'request_unit', None) or 'day'
        _logger.info(
            "[FAP-RECON] slip=%s %s emp=%s extra_type=%s(%s) request_unit=%s hours_per_day=%s "
            "target_remaining=%s payslip_total_avail=%s",
            self.id,
            label,
            emp.id,
            extra_type.id,
            extra_type.name,
            leave_type_unit,
            hours_per_day,
            self.remaining_extra_hours_balance,
            self.total_extra_hours_available,
        )

        allocations = Allocation.search([
            ('employee_id', '=', emp.id),
            ('holiday_status_id', '=', extra_type.id),
            ('state', '=', 'validate'),
        ])
        allocations.invalidate_recordset([
            'virtual_remaining_leaves', 'leaves_taken', 'max_leaves',
            'number_of_days', 'number_of_hours_display', 'type_request_unit',
        ])

        total_hours_via_virtual = 0.0
        total_alloc_days = 0.0
        total_virtual_days = 0.0
        total_taken_days = 0.0

        if not allocations:
            _logger.info("[FAP-RECON] slip=%s %s NO validated Extra Hours allocations", self.id, label)
        for alloc in allocations:
            unit = getattr(alloc, 'type_request_unit', None) or leave_type_unit or 'day'
            rem = float(getattr(alloc, 'virtual_remaining_leaves', 0.0) or 0.0)
            taken = float(getattr(alloc, 'leaves_taken', 0.0) or 0.0)
            max_l = float(getattr(alloc, 'max_leaves', 0.0) or 0.0)
            nod = float(alloc.number_of_days or 0.0)
            noh = float(getattr(alloc, 'number_of_hours_display', 0.0) or 0.0)
            if unit == 'hour':
                contrib_hours = rem
                contrib_days = rem / hours_per_day if hours_per_day else 0.0
            else:
                contrib_hours = rem * hours_per_day
                contrib_days = rem
            total_hours_via_virtual += contrib_hours
            total_alloc_days += nod
            total_virtual_days += contrib_days
            total_taken_days += taken if unit != 'hour' else (taken / hours_per_day if hours_per_day else 0.0)
            _logger.info(
                "[FAP-RECON] slip=%s %s ALLOC id=%s name=%r state=%s date_from=%s "
                "number_of_days=%s number_of_hours_display=%s unit=%s "
                "max_leaves=%s leaves_taken=%s virtual_remaining=%s "
                "contrib_hours=%s contrib_days=%s",
                self.id,
                label,
                alloc.id,
                alloc.name,
                alloc.state,
                alloc.date_from,
                nod,
                noh,
                unit,
                max_l,
                taken,
                rem,
                round(contrib_hours, 4),
                round(contrib_days, 4),
            )

        if Leave:
            leaves = Leave.search([
                ('employee_id', '=', emp.id),
                ('holiday_status_id', '=', extra_type.id),
                ('state', 'in', ['confirm', 'validate', 'validate1']),
            ], order='date_from desc', limit=30)
            if not leaves:
                _logger.info("[FAP-RECON] slip=%s %s NO Extra Hours leaves found", self.id, label)
            for lve in leaves:
                _logger.info(
                    "[FAP-RECON] slip=%s %s LEAVE id=%s name=%r state=%s "
                    "request=%s→%s number_of_days=%s number_of_hours=%s "
                    "holiday_allocation_id=%s",
                    self.id,
                    label,
                    lve.id,
                    lve.name,
                    lve.state,
                    lve.request_date_from,
                    lve.request_date_to,
                    lve.number_of_days,
                    getattr(lve, 'number_of_hours', None) or getattr(lve, 'number_of_hours_display', None),
                    getattr(lve, 'holiday_allocation_id', None).id if getattr(lve, 'holiday_allocation_id', None) else False,
                )
            # Focus on settlement / sync leaves in payslip period
            period_leaves = leaves.filtered(
                lambda l: l.request_date_from and self.date_from <= l.request_date_from <= self.date_to
            )
            _logger.info(
                "[FAP-RECON] slip=%s %s leaves_in_payslip_period=%s ids=%s",
                self.id,
                label,
                len(period_leaves),
                period_leaves.ids,
            )

        total_hours_via_virtual = round(total_hours_via_virtual, 2)
        _logger.info(
            "[FAP-RECON] slip=%s %s SUMMARY alloc_count=%s total_alloc_days=%s "
            "total_virtual_days=%s total_taken_days=%s total_hours_via_virtual=%s "
            "total_hours_if_alloc_days_x8=%s ui_likely_days=%s",
            self.id,
            label,
            len(allocations),
            round(total_alloc_days, 4),
            round(total_virtual_days, 4),
            round(total_taken_days, 4),
            total_hours_via_virtual,
            round(total_alloc_days * hours_per_day, 2),
            round(total_virtual_days, 4),
        )
        return total_hours_via_virtual

    def _fap_get_extra_hours_balance_hours(self, extra_type, exclude_alloc_names=None):
        """Return Extra Hours available in hours using the same remaining as Time Off dashboard."""
        self.ensure_one()
        exclude_alloc_names = set(exclude_alloc_names or [])
        Allocation = self.env['hr.leave.allocation'].sudo()
        emp = self.employee_id
        if not emp or not extra_type:
            return 0.0

        allocations = Allocation.search([
            ('employee_id', '=', emp.id),
            ('holiday_status_id', '=', extra_type.id),
            ('state', '=', 'validate'),
        ])
        if exclude_alloc_names:
            allocations = allocations.filtered(lambda a: (a.name or '') not in exclude_alloc_names)

        # Ensure computed remaining matches what Time Off dashboard shows
        allocations.invalidate_recordset([
            'virtual_remaining_leaves', 'leaves_taken', 'max_leaves',
            'number_of_days', 'number_of_hours_display',
        ])

        hours_per_day = 8.0
        try:
            if hasattr(emp, '_get_hours_per_day'):
                hours_per_day = emp._get_hours_per_day(self.date_to or fields.Date.context_today(self)) or 8.0
        except Exception:
            hours_per_day = 8.0

        hours = 0.0
        for alloc in allocations:
            # Prefer dashboard remaining (days). Fall back to allocated − taken.
            rem_days = getattr(alloc, 'virtual_remaining_leaves', None)
            if rem_days is None:
                max_leaves = getattr(alloc, 'max_leaves', None)
                taken = getattr(alloc, 'leaves_taken', 0.0) or 0.0
                if max_leaves is not None:
                    rem_days = max_leaves - taken
                else:
                    rem_days = (alloc.number_of_days or 0.0) - taken
            unit = getattr(alloc, 'type_request_unit', None) or getattr(extra_type, 'request_unit', None) or 'day'
            if unit == 'hour':
                # Some DBs store remaining already in hours for hour-based types
                hours += float(rem_days or 0.0)
            else:
                hours += float(rem_days or 0.0) * hours_per_day

        return round(hours, 2)

    def _fap_force_extra_hours_to_remaining(self, extra_type, alloc_name):
        """Make Time Off Extra Hours available match Remaining Extra Hours Balance."""
        self.ensure_one()
        Allocation = self.env['hr.leave.allocation'].sudo()
        target_hours = round(self.remaining_extra_hours_balance or 0.0, 2)

        # Reset this month's recon allocation / balance-sync leaves so we can recompute cleanly
        existing_alloc = Allocation.search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', extra_type.id),
            ('name', '=', alloc_name),
        ], limit=1)
        if existing_alloc:
            _logger.info(
                "[FAP-RECON] slip=%s removing old recon alloc=%s before force sync",
                self.id,
                existing_alloc.ids,
            )
            existing_alloc.write({'state': 'confirm'})
            existing_alloc.unlink()

        if 'hr.leave' in self.env:
            sync_leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('holiday_status_id', '=', extra_type.id),
                ('name', 'ilike', 'Extra Hours Balance Sync'),
                ('date_from', '<=', datetime.datetime.combine(self.date_to, datetime.time.max)),
                ('date_to', '>=', datetime.datetime.combine(self.date_from, datetime.time.min)),
            ])
            if sync_leaves:
                _logger.info(
                    "[FAP-RECON] slip=%s removing old balance-sync leaves=%s",
                    self.id,
                    sync_leaves.ids,
                )
                sync_leaves.write({'state': 'draft'})
                sync_leaves.unlink()

        # Flush so virtual_remaining sees removals
        self.env.flush_all()
        self._fap_log_extra_hours_snapshot(extra_type, label='BEFORE_FORCE')
        current_hours = self._fap_get_extra_hours_balance_hours(extra_type)
        gap_hours = round(target_hours - current_hours, 2)
        _logger.info(
            "[FAP-RECON] slip=%s FORCE Extra Hours current=%s target_remaining=%s gap=%s "
            "(current_days=%s target_days=%s)",
            self.id,
            current_hours,
            target_hours,
            gap_hours,
            round(current_hours / 8.0, 4),
            round(target_hours / 8.0, 4),
        )

        recon_alloc = self.env['hr.leave.allocation']
        if gap_hours > 0.01:
            # Need more Extra Hours → create monthly reconciliation allocation
            ot_days = round(gap_hours / 8.0, 4)
            alloc_vals = {
                'name': alloc_name,
                'employee_id': self.employee_id.id,
                'holiday_status_id': extra_type.id,
                'number_of_days': ot_days,
                'date_from': self.date_from,
            }
            if 'holiday_type' in Allocation._fields:
                alloc_vals['holiday_type'] = 'employee'
            if 'allocation_type' in Allocation._fields:
                alloc_vals['allocation_type'] = 'regular'
            recon_alloc = Allocation.with_context(
                employee_id=self.employee_id.id,
                mail_create_nolog=True,
                mail_notrack=True,
                tracking_disable=True,
                leave_fast_create=True,
                mail_activity_automation_skip=True,
            ).create(alloc_vals)
            self._fap_validate_allocation(recon_alloc)
            self.with_context(skip_reconcile_revert=True).sudo().write({
                'extra_hours_allocated_days': ot_days,
            })
            _logger.info(
                "[FAP-RECON] slip=%s FORCE added alloc=%s days=%s (+%sh)",
                self.id,
                recon_alloc.id,
                ot_days,
                gap_hours,
            )
        elif gap_hours < -0.01:
            # Need less Extra Hours → consume surplus via balance-sync leave
            surplus = abs(gap_hours)
            self._fap_create_balance_sync_leave(extra_type, surplus)
            self.with_context(skip_reconcile_revert=True).sudo().write({
                'extra_hours_allocated_days': 0.0,
            })
            _logger.info(
                "[FAP-RECON] slip=%s FORCE reduced Extra Hours by %sh via Balance Sync leave",
                self.id,
                surplus,
            )
        else:
            self.with_context(skip_reconcile_revert=True).sudo().write({
                'extra_hours_allocated_days': 0.0,
            })
            _logger.info("[FAP-RECON] slip=%s FORCE already matched (gap≈0)", self.id)

        # Second pass: correct residual gap (FIFO leave consumption can skew first pass)
        self.env.flush_all()
        final_hours = self._fap_get_extra_hours_balance_hours(extra_type)
        residual = round(target_hours - final_hours, 2)
        if abs(residual) > 0.05:
            _logger.info(
                "[FAP-RECON] slip=%s FORCE residual=%s after first pass — correcting",
                self.id,
                residual,
            )
            if residual > 0.05:
                # Increase recon allocation if we have one; else create
                recon_alloc = Allocation.search([
                    ('employee_id', '=', self.employee_id.id),
                    ('holiday_status_id', '=', extra_type.id),
                    ('name', '=', alloc_name),
                ], limit=1)
                add_days = round(residual / 8.0, 4)
                if recon_alloc:
                    new_days = round((recon_alloc.number_of_days or 0.0) + add_days, 4)
                    recon_alloc.write({'number_of_days': new_days})
                    self.with_context(skip_reconcile_revert=True).sudo().write({
                        'extra_hours_allocated_days': new_days,
                    })
                    _logger.info(
                        "[FAP-RECON] slip=%s FORCE 2nd pass increased alloc=%s to days=%s",
                        self.id,
                        recon_alloc.id,
                        new_days,
                    )
                else:
                    alloc_vals = {
                        'name': alloc_name,
                        'employee_id': self.employee_id.id,
                        'holiday_status_id': extra_type.id,
                        'number_of_days': add_days,
                        'date_from': self.date_from,
                    }
                    if 'holiday_type' in Allocation._fields:
                        alloc_vals['holiday_type'] = 'employee'
                    if 'allocation_type' in Allocation._fields:
                        alloc_vals['allocation_type'] = 'regular'
                    recon_alloc = Allocation.with_context(
                        employee_id=self.employee_id.id,
                        mail_create_nolog=True,
                        mail_notrack=True,
                        tracking_disable=True,
                        leave_fast_create=True,
                        mail_activity_automation_skip=True,
                    ).create(alloc_vals)
                    self._fap_validate_allocation(recon_alloc)
                    self.with_context(skip_reconcile_revert=True).sudo().write({
                        'extra_hours_allocated_days': add_days,
                    })
            elif residual < -0.05:
                self._fap_create_balance_sync_leave(extra_type, abs(residual))
            self.env.flush_all()
            final_hours = self._fap_get_extra_hours_balance_hours(extra_type)

        self.env.flush_all()
        snapshot_hours = self._fap_log_extra_hours_snapshot(extra_type, label='AFTER_FORCE')
        final_hours = self._fap_get_extra_hours_balance_hours(extra_type)
        _logger.info(
            "[FAP-RECON] slip=%s FORCE result Extra Hours hours=%s days=%s (target=%s) "
            "snapshot_hours=%s delta_vs_target=%s UI_days_if_virtual=%s",
            self.id,
            final_hours,
            round(final_hours / 8.0, 4),
            target_hours,
            snapshot_hours,
            round(final_hours - target_hours, 4),
            round(snapshot_hours / 8.0, 4),
        )

    def _fap_create_balance_sync_leave(self, leave_type, hours):
        """Consume Extra Hours surplus so Time Off matches Remaining (does not touch Lateness Settlement)."""
        self.ensure_one()
        if hours <= 0.01 or 'hr.leave' not in self.env or not leave_type:
            return

        Leave = self.env['hr.leave'].sudo()
        alloc = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
        ], order='date_to desc, id desc', limit=1)

        ctx_leave = Leave.with_context(
            employee_id=self.employee_id.id,
            mail_create_nolog=True,
            mail_notrack=True,
            tracking_disable=True,
            leave_skip_state_check=True,
            leave_skip_work_entries=True,
            no_work_entry=True,
            leave_skip_payslip_check=True,
            leave_skip_date_check=True,
            skip_payslip_validation=True,
            payslip_skip_leave_check=True,
            leave_fast_create=True,
        )

        remaining_hours = hours
        curr_d = self.date_from
        created_ids = []
        while curr_d <= self.date_to and remaining_hours >= 7.99:
            dt_start = datetime.datetime.combine(curr_d, datetime.time(8, 0, 0))
            dt_stop = datetime.datetime.combine(curr_d, datetime.time(17, 0, 0))
            vals = {
                'name': f"Extra Hours Balance Sync - {curr_d.strftime('%d/%m/%Y')}",
                'employee_id': self.employee_id.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': curr_d,
                'request_date_to': curr_d,
                'date_from': dt_start,
                'date_to': dt_stop,
                'number_of_days': 1.0,
                'state': 'validate',
            }
            if alloc and 'holiday_allocation_id' in Leave._fields:
                vals['holiday_allocation_id'] = alloc.id
            try:
                new_lve = ctx_leave.create(vals)
                new_lve.sudo().write({'state': 'validate'})
                created_ids.append(new_lve.id)
                _logger.info(
                    "[FAP-RECON] slip=%s Balance Sync FULL-DAY leave created id=%s days=1.0 state=%s",
                    self.id,
                    new_lve.id,
                    new_lve.state,
                )
            except Exception:
                _logger.exception(
                    "[FAP-RECON] slip=%s balance sync full-day leave FAILED vals=%s",
                    self.id,
                    vals,
                )
            remaining_hours -= 8.0
            curr_d += datetime.timedelta(days=1)

        if remaining_hours > 0.01 and curr_d <= self.date_to:
            frac_hours = round(remaining_hours, 2)
            frac_days = round(frac_hours / 8.0, 4)
            dt_start = datetime.datetime.combine(curr_d, datetime.time(8, 0, 0))
            dt_stop = dt_start + datetime.timedelta(hours=frac_hours)
            vals = {
                'name': f"Extra Hours Balance Sync - {frac_hours}h ({curr_d.strftime('%d/%m/%Y')})",
                'employee_id': self.employee_id.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': curr_d,
                'request_date_to': curr_d,
                'date_from': dt_start,
                'date_to': dt_stop,
                'number_of_days': frac_days,
                'state': 'validate',
            }
            if alloc and 'holiday_allocation_id' in Leave._fields:
                vals['holiday_allocation_id'] = alloc.id
            try:
                new_lve = ctx_leave.create(vals)
                new_lve.sudo().write({'state': 'validate'})
                created_ids.append(new_lve.id)
                _logger.info(
                    "[FAP-RECON] slip=%s Balance Sync FRAC leave created id=%s "
                    "hours=%s days=%s state=%s",
                    self.id,
                    new_lve.id,
                    frac_hours,
                    frac_days,
                    new_lve.state,
                )
            except Exception:
                _logger.exception(
                    "[FAP-RECON] slip=%s balance sync fractional leave FAILED vals=%s",
                    self.id,
                    vals,
                )
        elif remaining_hours > 0.01 and curr_d > self.date_to:
            _logger.error(
                "[FAP-RECON] slip=%s Balance Sync could not place remaining %sh — "
                "no days left in payslip period %s→%s",
                self.id,
                remaining_hours,
                self.date_from,
                self.date_to,
            )

        _logger.info(
            "[FAP-RECON] slip=%s Balance Sync DONE requested_hours=%s created_leave_ids=%s",
            self.id,
            hours,
            created_ids,
        )

    def _fap_validate_allocation(self, allocation):
        """Approve allocation to validated state (Odoo 19-safe)."""
        if not allocation:
            return allocation
        allocation = allocation.sudo()
        _logger.info(
            "[FAP-RECON] _fap_validate_allocation alloc=%s state=%s validation_type=%s",
            allocation.id,
            allocation.state,
            getattr(allocation, 'validation_type', None),
        )
        try:
            if allocation.state == 'validate':
                return allocation
            if hasattr(allocation, 'action_approve'):
                try:
                    allocation.action_approve()
                    allocation.invalidate_recordset()
                    if allocation.state == 'validate':
                        _logger.info("[FAP-RECON] alloc=%s approved via action_approve", allocation.id)
                        return allocation
                    if allocation.state == 'validate1' and hasattr(allocation, '_action_validate'):
                        allocation._action_validate()
                        _logger.info("[FAP-RECON] alloc=%s validated via _action_validate", allocation.id)
                        return allocation
                except Exception:
                    _logger.exception(
                        "[FAP-RECON] alloc=%s action_approve failed — trying direct state write",
                        allocation.id,
                    )
            allocation.with_context(tracking_disable=True, mail_notrack=True).write({'state': 'validate'})
            _logger.info("[FAP-RECON] alloc=%s forced state=validate", allocation.id)
        except Exception:
            _logger.exception("[FAP-RECON] _fap_validate_allocation FAILED alloc=%s", allocation.id)
            raise
        return allocation

    def _revert_reconciliation_settlements(self):
        _logger.info("[FAP-RECON] _revert_reconciliation_settlements START slips=%s", self.ids)
        Leave = self.env['hr.leave'].sudo() if 'hr.leave' in self.env else None
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None

        for payslip in self:
            if not payslip.employee_id or not payslip.date_to:
                continue

            was_reconciled = getattr(payslip, 'is_reconciled', False)
            _logger.info(
                "[FAP-RECON] revert slip=%s state=%s is_reconciled=%s",
                payslip.id,
                payslip.state,
                was_reconciled,
            )
            if not was_reconciled and payslip.state in ['draft', 'verify']:
                _logger.info("[FAP-RECON] revert slip=%s SKIP (not reconciled)", payslip.id)
                continue

            if 'is_reconciled' in payslip._fields and payslip.is_reconciled:
                payslip.with_context(skip_reconcile_revert=True).sudo().write({'is_reconciled': False})

            emp = payslip.employee_id
            if emp:
                pre_recon_ot = round(payslip.total_extra_hours_available, 2)
                for field_name in ['total_overtime', 'total_extra_hours', 'extra_hours_balance', 'overtime_balance']:
                    if field_name in emp._fields:
                        try:
                            emp.sudo().write({field_name: pre_recon_ot})
                        except Exception as e:
                            _logger.warning(
                                "[FAP-RECON] Could not revert %s on employee %s: %s",
                                field_name, emp.id, e,
                            )

            if Leave:
                try:
                    month_leaves = Leave.search([
                        ('employee_id', '=', payslip.employee_id.id),
                        '|',
                        ('name', 'ilike', 'Lateness Settlement'),
                        ('name', 'ilike', 'Extra Hours Balance Sync'),
                        ('date_from', '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max)),
                        ('date_to', '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                    ])
                    _logger.info(
                        "[FAP-RECON] revert slip=%s settlement/sync leaves=%s",
                        payslip.id,
                        month_leaves.ids,
                    )
                    if month_leaves:
                        month_leaves.write({'state': 'draft'})
                        month_leaves.unlink()
                except Exception:
                    _logger.exception("[FAP-RECON] revert slip=%s leave unlink failed", payslip.id)

            if Allocation:
                try:
                    month_str = payslip.date_to.strftime('%B %Y') if payslip.date_to else ''
                    alloc_name = f"Extra Hours Reconciliation: {month_str} - {payslip.employee_id.name}"
                    month_allocs = Allocation.search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('name', '=', alloc_name),
                    ])
                    _logger.info(
                        "[FAP-RECON] revert slip=%s recon allocs=%s name=%r",
                        payslip.id,
                        month_allocs.ids,
                        alloc_name,
                    )
                    if month_allocs:
                        month_allocs.write({'state': 'confirm'})
                        month_allocs.unlink()
                except Exception:
                    _logger.exception("[FAP-RECON] revert slip=%s alloc unlink failed", payslip.id)

            if 'extra_hours_allocated_days' in payslip._fields:
                payslip.with_context(skip_reconcile_revert=True).sudo().write({
                    'extra_hours_allocated_days': 0.0,
                })

        _logger.info("[FAP-RECON] _revert_reconciliation_settlements END slips=%s", self.ids)

    def _get_previous_extra_hours_balance(self):
        """Return Extra Hours available before this payslip (hours), from leave allocations."""
        self.ensure_one()
        if not self.employee_id:
            return 0.0

        LeaveType = self.env['hr.leave.type'].sudo() if 'hr.leave.type' in self.env else None
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None
        Leave = self.env['hr.leave'].sudo() if 'hr.leave' in self.env else None

        if LeaveType is not None and Allocation is not None:
            extra_types = LeaveType.search([
                '|', '|',
                ('name', '=', 'Extra Hours'),
                ('name', 'ilike', 'Extra Hours'),
                ('name', 'ilike', 'إضافي'),
            ])
            if extra_types:
                month_str = self.date_to.strftime('%B %Y') if self.date_to else ''
                current_alloc_name = f"Extra Hours Reconciliation: {month_str} - {self.employee_id.name}"

                allocations = Allocation.search([
                    ('employee_id', '=', self.employee_id.id),
                    ('holiday_status_id', 'in', extra_types.ids),
                    ('state', '=', 'validate'),
                ])
                hours = 0.0
                for alloc in allocations:
                    if (alloc.name or '') == current_alloc_name:
                        continue
                    if alloc.number_of_days:
                        hours += alloc.number_of_days * 8.0
                    elif getattr(alloc, 'number_of_hours_display', None):
                        hours += alloc.number_of_hours_display

                if Leave:
                    leaves = Leave.search([
                        ('employee_id', '=', self.employee_id.id),
                        ('holiday_status_id', 'in', extra_types.ids),
                        ('state', '=', 'validate'),
                    ])
                    for lve in leaves:
                        if lve.number_of_days:
                            hours -= lve.number_of_days * 8.0
                        elif getattr(lve, 'number_of_hours', None):
                            hours -= lve.number_of_hours
                        elif getattr(lve, 'number_of_hours_display', None):
                            hours -= lve.number_of_hours_display

                return max(0.0, round(hours, 2))

        if 'hr.attendance.overtime.line' not in self.env:
            return 0.0
        lines = self.env['hr.attendance.overtime.line'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '<', self.date_from),
            ('compensable_as_leave', '=', True),
            ('status', '=', 'approved'),
        ])
        return max(0.0, sum(lines.mapped('duration')))
