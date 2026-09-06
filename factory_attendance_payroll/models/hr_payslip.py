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
        if target_type_ids:
            allocations = self.env['hr.leave.allocation'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('state', '=', 'validate'),
                ('holiday_status_id', 'in', target_type_ids)
            ])
            for alloc in allocations:
                if 'Extra Hours Reconciliation' in (alloc.name or '') or 'Monthly Overtime Earned' in (alloc.name or ''):
                    continue
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

            taken_leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('state', '=', 'validate'),
                ('holiday_status_id', 'in', target_type_ids),
                '!', ('name', 'ilike', 'Lateness Settlement')
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

        for payslip in valid_slips:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                payslip.attendance_gross_overtime = 0.0
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

            for att_date, raw_hrs in daily_hours.items():
                if raw_hrs >= 6.0:
                    net_hrs = max(0.0, raw_hrs - break_hrs)
                elif raw_hrs > 4.0:
                    net_hrs = max(0.0, raw_hrs - (break_hrs / 2.0))
                else:
                    net_hrs = raw_hrs

                is_holiday = att_date in public_holiday_dates
                matching_atts = [a for a in emp_attendances if a.check_in.date() == att_date]
                is_approved = (
                    approved_ot_by_emp_date.get((emp_id, att_date), 0.0) > 0 or
                    any(getattr(a, 'overtime_status', False) == 'approved' or getattr(a, 'validated_overtime_hours', 0.0) > 0 for a in matching_atts)
                )

                if is_holiday:
                    if allow_ot and net_hrs > 0 and is_approved:
                        total_ot += (net_hrs * 1.5)
                    continue

                standard_target = 8.0
                if net_hrs > standard_target:
                    ot_excess = net_hrs - standard_target
                    if ot_excess >= min_ot_threshold and allow_ot and is_approved:
                        approved_hrs = approved_ot_by_emp_date.get((emp_id, att_date), 0.0)
                        if not approved_hrs:
                            approved_hrs = ot_excess
                        total_ot += (approved_hrs * 1.25)
                elif net_hrs < standard_target:
                    shortfall = standard_target - net_hrs
                    if shortfall > min_lateness_threshold:
                        total_undertime += shortfall

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

            gross_ot = round(total_ot, 2)
            gross_ut = round(total_undertime, 2)

            payslip.attendance_gross_overtime = gross_ot
            payslip.attendance_gross_undertime = gross_ut
            payslip.attendance_net_reconciled = round(gross_ot - gross_ut, 2)

            current_slip_allocated_hours = (payslip.extra_hours_allocated_days or 0.0) * 8.0
            prior_alloc_extra = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in extra_type_ids) - current_slip_allocated_hours)
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

        self._convert_flexible_rest_days_to_ars()

        res = super().compute_sheet()
        self.write({'is_reconciled': True})
        return res

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

            # 1. CLEAR_EXTRA (Termination: Extra Hours Settlement)
            ot_hrs = round(slip.remaining_extra_hours_balance or slip.total_extra_hours_available, 2)
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

            # 2. CLEAR_ANNUAL (Termination: Annual Leave Settlement)
            annual_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'CLEAR_ANNUAL')], limit=1)
            if annual_type:
                annual_amount = round(annual_leave_days * daily_rate, 3)
                annual_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == annual_type)
                if annual_line:
                    annual_line.write({'quantity': annual_leave_days, 'amount': annual_amount})
                else:
                    if slip.id:
                        input_model.create({
                            'payslip_id': slip.id,
                            'input_type_id': annual_type.id,
                            'quantity': annual_leave_days,
                            'amount': annual_amount,
                        })
                    else:
                        slip.input_line_ids += input_model.new({
                            'payslip_id': slip.id,
                            'input_type_id': annual_type.id,
                            'quantity': annual_leave_days,
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
        self._apply_termination_clearance_inputs()

    def action_payslip_done(self):
        res = super().action_payslip_done()
        self._sync_reconciliation_settlements()
        return res

    def action_payslip_draft(self):
        self._revert_reconciliation_settlements()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        self._revert_reconciliation_settlements()
        return super().action_payslip_cancel()

    def action_cancel(self):
        self._revert_reconciliation_settlements()
        return super().action_cancel() if hasattr(super(), 'action_cancel') else True

    def unlink(self):
        self._revert_reconciliation_settlements()
        return super().unlink()

    def write(self, vals):
        if vals.get('state') == 'cancel' and not self._context.get('skip_reconcile_revert'):
            self.with_context(skip_reconcile_revert=True)._revert_reconciliation_settlements()
        return super().write(vals)

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
                raw = att.worked_hours or 0.0
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
                        line['number_of_days'] = round(total_regular_attendance_hrs / 8.0, 2)
                        line['amount'] = round(total_regular_attendance_hrs * hourly_rate, 3)
                        filtered_lines.append(line)

                elif code in ['GTO', 'PHD', 'HOLIDAY', 'LEAVE110', 'PHW', 'HOLIDAY_WORKED'] or 'public holiday' in we_name or 'holiday' in we_name:
                    if total_holiday_worked_hrs > 0.01:
                        weighted_hol_hrs = round(total_holiday_worked_hrs * 1.5, 2)
                        line['number_of_hours'] = weighted_hol_hrs
                        line['number_of_days'] = round(weighted_hol_hrs / 8.0, 2)
                        line['amount'] = round(weighted_hol_hrs * hourly_rate, 3)
                    else:
                        base_hrs = line.get('number_of_hours') or 8.0
                        line['number_of_hours'] = base_hrs
                        line['number_of_days'] = round(base_hrs / 8.0, 2)
                        line['amount'] = round(base_hrs * hourly_rate, 3)
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
                emp_id = payslip.employee_id.id
                slip_worked_dates = set(
                    d for d in worked_dates_by_emp.get(emp_id, set())
                    if payslip.date_from <= d <= payslip.date_to
                )
                emp_work_entries = we_by_emp.get(emp_id, [])
                for we in emp_work_entries:
                    code = (we.work_entry_type_id.code or '').strip()
                    if not we.work_entry_type_id.is_leave and code not in ['LEAVE500', 'UNPAID', 'ABSENT', 'ABS']:
                        we_date = getattr(we, 'date', False) or (we.date_start.date() if hasattr(we, 'date_start') and we.date_start else False)
                        if isinstance(we_date, datetime.datetime):
                            we_date = we_date.date()
                        if we_date:
                            slip_worked_dates.add(we_date)

                allowed_rest_days = len(slip_worked_dates) // 6
                converted_count = 0
                for we in emp_work_entries:
                    code = (we.work_entry_type_id.code or '').strip()
                    name = (we.work_entry_type_id.name or '').lower()
                    if code in ['LEAVE500', 'UNPAID', 'ABSENT', 'ABS'] or 'absent' in name:
                        if converted_count < allowed_rest_days:
                            to_update |= we
                            converted_count += 1
            except Exception:
                pass

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
        LeaveType = self.env['hr.leave.type'].sudo() if 'hr.leave.type' in self.env else None
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None

        for payslip in self:
            if not payslip.employee_id or not payslip.date_to:
                continue

            month_str = payslip.date_to.strftime('%B %Y') if payslip.date_to else ''

            if Allocation and LeaveType:
                extra_types = LeaveType.search(['|', '|', ('name', '=', 'Extra Hours'), ('name', 'ilike', 'Extra Hours'), ('name', 'ilike', 'إضافي')])
                extra_type = extra_types[0] if extra_types else None
                if extra_type:
                    alloc_name = f"Extra Hours Reconciliation: {month_str} - {payslip.employee_id.name}"
                    existing_alloc = Allocation.search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('holiday_status_id', '=', extra_type.id),
                        ('name', '=', alloc_name),
                    ], limit=1)

                    prev_bal = payslip._get_previous_extra_hours_balance()
                    net_ot_hours = round(max(0.0, payslip.remaining_extra_hours_balance - prev_bal), 4) if payslip.remaining_extra_hours_balance > prev_bal else 0.0

                    if net_ot_hours > 0.01:
                        ot_days = round(net_ot_hours / 8.0, 4)
                        alloc_vals = {
                            'name': alloc_name,
                            'holiday_type': 'employee',
                            'employee_id': payslip.employee_id.id,
                            'holiday_status_id': extra_type.id,
                            'number_of_days': ot_days,
                            'state': 'validate',
                        }
                        if existing_alloc:
                            existing_alloc.write(alloc_vals)
                        else:
                            Allocation.with_context(
                                employee_id=payslip.employee_id.id,
                                mail_create_nolog=True,
                                mail_notrack=True,
                                tracking_disable=True,
                            ).create(alloc_vals)
                    elif existing_alloc:
                        existing_alloc.unlink()

            payslip._create_or_update_settlement_leave('Extra Hours', payslip.lateness_covered_by_extra_hours, 'Extra Hours Settlement')
            payslip._create_or_update_settlement_leave('Annual Leave', payslip.lateness_covered_by_annual_leave, 'Annual Leave Settlement')

    def _revert_reconciliation_settlements(self):
        Leave = self.env['hr.leave'].sudo() if 'hr.leave' in self.env else None
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None

        for payslip in self:
            if not payslip.employee_id or not payslip.date_to:
                continue

            was_reconciled = getattr(payslip, 'is_reconciled', False)
            if not was_reconciled and payslip.state in ['draft', 'verify']:
                continue

            if 'is_reconciled' in payslip._fields and payslip.is_reconciled:
                payslip.with_context(skip_reconcile_revert=True).sudo().write({'is_reconciled': False})

            if Leave:
                try:
                    month_leaves = Leave.search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('name', 'ilike', 'Lateness Settlement'),
                        ('date_from', '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max)),
                        ('date_to', '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                    ])
                    if month_leaves:
                        month_leaves.write({'state': 'draft'})
                        month_leaves.unlink()
                except Exception:
                    pass

            if Allocation:
                try:
                    month_str = payslip.date_to.strftime('%B %Y') if payslip.date_to else ''
                    alloc_name = f"Extra Hours Reconciliation: {month_str} - {payslip.employee_id.name}"
                    month_allocs = Allocation.search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('name', '=', alloc_name),
                    ])
                    if month_allocs:
                        month_allocs.write({'state': 'draft'})
                        month_allocs.unlink()
                except Exception:
                    pass

    def _get_previous_extra_hours_balance(self):
        self.ensure_one()
        if not self.employee_id or 'hr.attendance.overtime.line' not in self.env:
            return 0.0
        lines = self.env['hr.attendance.overtime.line'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '<', self.date_from),
            ('compensable_as_leave', '=', True),
            ('status', '=', 'approved'),
        ])
        return max(0.0, sum(lines.mapped('duration')))
