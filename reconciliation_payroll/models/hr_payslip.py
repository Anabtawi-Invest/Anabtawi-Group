# -*- coding: utf-8 -*-

from collections import defaultdict
import datetime
import logging
from odoo import models, fields, api

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
        help="Weekly rest days taken this month."
    )
    attendance_gross_undertime = fields.Float(
        string="Monthly Lateness / Undertime",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Total lateness and undertime hours accumulated during the month."
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
        help="Remaining Extra Hours available after settling Step 1 Lateness."
    )

    # 3-Step Lateness Settlement Audit Breakdown
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

    attendance_net_reconciled = fields.Float(
        string="Net Reconciled Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True
    )
    is_reconciled = fields.Boolean(
        string="Attendance Reconciled",
        default=False,
        copy=False
    )
    extra_hours_allocated_days = fields.Float(
        string="Extra Hours Added to Allocation",
        default=0.0,
        copy=False
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        if not getattr(self.env.registry, 'ready', True) or self.env.context.get('install_mode') or self.env.context.get('module_installation'):
            self._reset_reconciliation_fields()
            return

        valid_slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to and (s.state in ['draft', 'verify'] or not s.id))
        (self - valid_slips)._reset_reconciliation_fields(only_if_empty=True)

        if not valid_slips:
            return

        emp_ids = valid_slips.mapped('employee_id').ids
        min_date = min(valid_slips.mapped('date_from'))
        max_date = max(valid_slips.mapped('date_to'))

        # Pre-fetch public holidays
        public_holiday_dates = self.env['hr.attendance']._get_public_holiday_dates_batch(min_date, max_date)

        # Pre-fetch attendances
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', emp_ids),
            ('check_in', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
            ('check_in', '<=', datetime.datetime.combine(max_date, datetime.time.max))
        ])
        att_by_emp = defaultdict(list)
        for att in attendances:
            att_by_emp[att.employee_id.id].append(att)

        # Pre-fetch approved overtime lines if module exists
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

        # Pre-fetch leave allocations & balances
        LeaveType = self.env['hr.leave.type'].sudo()
        extra_types = LeaveType.search(['|', '|', ('name', '=', 'Extra Hours'), ('name', 'ilike', 'Extra Hours'), ('name', 'ilike', 'إضافي')])
        annual_types = LeaveType.search(['|', '|', ('name', '=', 'Annual Leave'), ('name', 'ilike', 'Annual Leave'), ('name', 'ilike', 'سنوي')])

        extra_type_ids = set(extra_types.ids)
        annual_type_ids = set(annual_types.ids)
        target_type_ids = list(extra_type_ids | annual_type_ids)

        alloc_hours_by_emp_type = defaultdict(float)
        recon_alloc_hours_by_emp_name = {}

        if target_type_ids and 'hr.leave.allocation' in self.env:
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
                alloc_hours_by_emp_type[(alloc.employee_id.id, alloc.holiday_status_id.id)] += hrs
                if 'Extra Hours Reconciliation' in (alloc.name or ''):
                    recon_alloc_hours_by_emp_name[(alloc.employee_id.id, alloc.name or '')] = hrs

            if 'hr.leave' in self.env:
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
                    alloc_hours_by_emp_type[(lve.employee_id.id, lve.holiday_status_id.id)] -= hrs

        # Pre-fetch approved leave dates
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
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to or payslip.employee_id.is_manager_exempt():
                payslip._reset_reconciliation_fields()
                continue

            emp_id = payslip.employee_id.id
            emp_atts = [a for a in att_by_emp.get(emp_id, []) if payslip.date_from <= a.check_in.date() <= payslip.date_to]
            company = payslip.company_id or self.env.company
            allow_ot = getattr(company, 'enable_overtime_calculation', True)

            # 1. Overtime Calculation (Strict Approval Enforcement)
            total_ot = 0.0
            if allow_ot:
                for att_date in set(a.check_in.date() for a in emp_atts if a.check_in):
                    matching = [a for a in emp_atts if a.check_in and a.check_in.date() == att_date]
                    is_holiday = att_date in public_holiday_dates or any(getattr(a, 'is_public_holiday', False) for a in matching)
                    is_approved = (
                        approved_ot_by_emp_date.get((emp_id, att_date), 0.0) > 0 or
                        any(getattr(a, 'overtime_status', False) == 'approved' or getattr(a, 'validated_overtime_hours', 0.0) > 0 for a in matching)
                    )
                    if not is_approved:
                        continue

                    if is_holiday:
                        net_hol_hrs = sum(getattr(a, 'net_worked_hours', 0.0) or a.worked_hours for a in matching)
                        if net_hol_hrs > 0:
                            total_ot += (net_hol_hrs * 1.5)
                    else:
                        day_ot = sum(
                            getattr(a, 'validated_overtime_hours', 0.0) or getattr(a, 'daily_overtime_hours', 0.0)
                            for a in matching
                            if getattr(a, 'overtime_status', False) == 'approved' or getattr(a, 'validated_overtime_hours', 0.0) > 0
                        )
                        if day_ot >= 0.75:
                            total_ot += (day_ot * 1.25)

            # 2. Daily Punch Lateness
            daily_punch_lateness = sum(
                att.daily_undertime_hours for att in emp_atts
                if not getattr(att, 'is_public_holiday', False) and hasattr(att, 'daily_undertime_hours') and att.daily_undertime_hours
            )

            # 3. Absent Work Entries Duration
            absent_hours = 0.0
            if 'hr.work.entry' in self.env:
                WEModel = self.env['hr.work.entry']
                we_domain = [
                    ('employee_id', '=', emp_id),
                    ('state', '!=', 'cancelled'),
                    '|', ('work_entry_type_id.code', 'in', ['ABSENT', 'ABS']),
                    ('work_entry_type_id.display_code', 'in', ['ABSENT', 'ABS']),
                ]
                if 'date' in WEModel._fields:
                    we_domain += [('date', '>=', payslip.date_from), ('date', '<=', payslip.date_to)]
                elif 'date_start' in WEModel._fields:
                    we_domain += [
                        ('date_start', '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                        ('date_start', '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max)),
                    ]
                abs_entries = WEModel.sudo().search(we_domain)
                absent_hours = sum(getattr(we, 'duration', 8.0) or 8.0 for we in abs_entries)

            total_undertime = daily_punch_lateness + absent_hours

            # 4. Rest days evaluation (4 days allowance; unused adds to OT if employee worked)
            total_days_in_month = (payslip.date_to - payslip.date_from).days + 1
            daily_dates = set(a.check_in.date() for a in emp_atts if a.check_in)
            worked_days_count = len(daily_dates)
            emp_leave_dates = leave_dates_by_emp.get(emp_id, set())

            approved_leave_days_count = sum(
                1 for d in range(total_days_in_month)
                if (payslip.date_from + datetime.timedelta(days=d)) not in daily_dates
                and ((payslip.date_from + datetime.timedelta(days=d)) in emp_leave_dates or
                     (payslip.date_from + datetime.timedelta(days=d)) in public_holiday_dates)
            )

            if worked_days_count > 0:
                rest_days_taken = max(0, total_days_in_month - worked_days_count - approved_leave_days_count)
                unused_rest_days = max(0, 4 - rest_days_taken)
            else:
                rest_days_taken = 0
                unused_rest_days = 0

            if allow_ot and unused_rest_days > 0 and worked_days_count > 0:
                total_ot += (unused_rest_days * 8.0 * 1.5)

            gross_ot = round(total_ot, 2)
            gross_ut = round(total_undertime, 2)

            payslip.attendance_gross_overtime = gross_ot
            payslip.rest_days_taken = float(rest_days_taken)
            payslip.attendance_gross_undertime = gross_ut
            payslip.attendance_net_reconciled = round(gross_ot - gross_ut, 2)

            # Previous banked extra hours
            month_str = payslip.date_to.strftime('%B %Y') if payslip.date_to else ''
            curr_recon_name = f"Extra Hours Reconciliation: {month_str} - {payslip.employee_id.name}"
            exclude_recon_hrs = recon_alloc_hours_by_emp_name.get((emp_id, curr_recon_name), 0.0)
            prior_alloc_extra = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in extra_type_ids) - exclude_recon_hrs)
            prior_ot_line_extra = round(banked_extra_by_emp.get(emp_id, 0.0), 2)
            prev_extra_hours = max(prior_alloc_extra, prior_ot_line_extra)

            total_extra_avail = round(prev_extra_hours + gross_ot, 2)
            payslip.total_extra_hours_available = total_extra_avail

            # 3-Step Lateness Settlement
            covered_extra = round(min(gross_ut, total_extra_avail), 2)
            rem_lateness = round(gross_ut - covered_extra, 2)

            covered_annual_leave = 0.0
            if rem_lateness > 0.01 and payslip.employee_id.allow_annual_leave_lateness_deduction:
                annual_avail = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in annual_type_ids))
                covered_annual_leave = round(min(rem_lateness, annual_avail), 2)
                rem_lateness = round(rem_lateness - covered_annual_leave, 2)

            payslip.lateness_covered_by_extra_hours = covered_extra
            payslip.remaining_extra_hours_balance = round(max(0.0, total_extra_avail - covered_extra), 2)
            payslip.lateness_covered_by_annual_leave = covered_annual_leave
            payslip.undertime_cash_deduction_hours = rem_lateness if rem_lateness >= 0.01 else 0.0

    def _reset_reconciliation_fields(self, only_if_empty=False):
        for s in self:
            if only_if_empty and (s.attendance_gross_overtime or s.attendance_gross_undertime):
                continue
            s.attendance_gross_overtime = 0.0
            s.rest_days_taken = 0.0
            s.attendance_gross_undertime = 0.0
            s.attendance_net_reconciled = 0.0
            s.total_extra_hours_available = 0.0
            s.lateness_covered_by_extra_hours = 0.0
            s.lateness_covered_by_annual_leave = 0.0
            s.remaining_extra_hours_balance = 0.0
            s.undertime_cash_deduction_hours = 0.0

    def compute_sheet(self):
        valid = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to)
        if valid:
            valid._compute_attendance_reconciliation_fields()
            valid._apply_termination_clearance_inputs()
        res = super().compute_sheet()
        self.write({'is_reconciled': True})
        return res

    def _get_worked_day_lines(self, *args, **kwargs):
        """
        Builds worked day lines aligning attendance logs, earned rest days,
        unworked holidays, distinct absent entries, and undertime deductions.
        """
        res = super()._get_worked_day_lines(*args, **kwargs)
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue

            emp = payslip.employee_id
            if hasattr(emp, '_create_absent_work_entries_for_period'):
                emp._create_absent_work_entries_for_period(payslip.date_from, payslip.date_to)

            w = emp.wage or 0.0
            break_hrs = emp._get_lunch_break_duration()

            attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', emp.id),
                ('check_in', '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                ('check_in', '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max))
            ])

            cal_id = emp.resource_calendar_id.id if emp.resource_calendar_id else False
            holiday_dates = set(self.env['hr.attendance']._get_public_holiday_dates_batch(payslip.date_from, payslip.date_to, calendar_id=cal_id))

            regular_atts = attendances.filtered(lambda a: a.check_in.date() not in holiday_dates)
            holiday_atts = attendances.filtered(lambda a: a.check_in.date() in holiday_dates)

            def _net_hrs(att):
                if hasattr(att, 'net_worked_hours') and att.net_worked_hours:
                    return att.net_worked_hours
                raw = (att.check_out - att.check_in).total_seconds() / 3600.0 if (att.check_in and att.check_out) else (att.worked_hours or 0.0)
                if raw >= 6.0:
                    return max(0.0, raw - break_hrs)
                elif raw > 4.0:
                    return max(0.0, raw - (break_hrs / 2.0))
                return raw

            total_reg_hrs = round(sum(_net_hrs(a) for a in regular_atts), 2)
            total_hol_hrs = round(sum(_net_hrs(a) for a in holiday_atts), 2)
            rem_cash_deduction_hrs = round(payslip.undertime_cash_deduction_hours or 0.0, 2)

            total_scheduled_hrs = total_reg_hrs + total_hol_hrs + rem_cash_deduction_hrs
            if total_scheduled_hrs > 0:
                hourly_rate = round(w / total_scheduled_hrs, 4)
            else:
                hourly_rate = round((w / 26.0) / 8.0, 4)

            # Contract boundaries
            c_start = payslip.date_from
            c_end = payslip.date_to
            ContractModel = self.env.get('hr.contract')
            if ContractModel is not None:
                contracts = ContractModel.sudo().search([('employee_id', '=', emp.id), ('state', 'in', ['open', 'close'])])
                if contracts:
                    valid_starts = [c.date_start for c in contracts if c.date_start]
                    if valid_starts and min(valid_starts) > payslip.date_from:
                        c_start = min(valid_starts)
                    valid_ends = [c.date_end for c in contracts if c.date_end]
                    if valid_ends and len(valid_ends) == len(contracts) and max(valid_ends) < payslip.date_to:
                        c_end = max(valid_ends)

            reg_physical_days = float(len(set(a.check_in.date() for a in regular_atts if a.check_in)))
            work_station = getattr(emp, 'employee_work_station', False) or 'factory'

            if work_station == 'headoffice':
                cal = emp.resource_calendar_id
                working_weekdays = set(int(a.dayofweek) for a in cal.attendance_ids if a.dayofweek is not None) if cal else {0, 1, 2, 3, 5}
                month_rest_days = sum(1 for d_idx in range((payslip.date_to - payslip.date_from).days + 1) if (payslip.date_from + datetime.timedelta(days=d_idx)).weekday() not in working_weekdays)
            else:
                target_wd = 0 if work_station == 'factory' else 4
                month_rest_days = sum(1 for d_idx in range((payslip.date_to - payslip.date_from).days + 1) if (payslip.date_from + datetime.timedelta(days=d_idx)).weekday() == target_wd)

            earned_rest_days = min(month_rest_days, int(reg_physical_days // 6)) if reg_physical_days > 0 else month_rest_days

            active_holidays = [d for d in holiday_dates if c_start <= d <= c_end]
            unworked_holidays = len([d for d in active_holidays if d not in set(a.check_in.date() for a in holiday_atts if a.check_in)])

            final_attendance_days = float(round(reg_physical_days + earned_rest_days + unworked_holidays))

            # Filter and reconstruct worked days lines
            filtered_lines = []
            added = set()

            for line in res:
                code = (line.get('code') or '').strip().upper()
                name = (line.get('name') or '').lower()

                if 'settlement' in name or 'lateness' in name:
                    continue
                if code in ['ARS', 'REST', 'RESTDAY']:
                    continue

                if code in ['WORK100', 'ATTENDANCE', 'WORK'] or 'attendance' in name:
                    if 'ATTENDANCE' in added:
                        continue
                    added.add('ATTENDANCE')
                    line['number_of_days'] = final_attendance_days
                    line['number_of_hours'] = total_reg_hrs if total_reg_hrs > 0 else round(final_attendance_days * 8.0, 2)
                    line['amount'] = round((total_reg_hrs if total_reg_hrs > 0 else final_attendance_days * 8.0) * hourly_rate, 3)
                    filtered_lines.append(line)

                elif code in ['GTO', 'PHD', 'HOLIDAY'] or 'holiday' in name:
                    if 'HOLIDAY' in added:
                        continue
                    added.add('HOLIDAY')
                    if total_hol_hrs > 0.01:
                        weighted_hrs = round(total_hol_hrs * 1.5, 2)
                        line['number_of_hours'] = weighted_hrs
                        line['number_of_days'] = float(len(set(a.check_in.date() for a in holiday_atts)))
                        line['amount'] = round(weighted_hrs * hourly_rate, 3)
                        filtered_lines.append(line)

                elif code in ['ABSENT', 'ABS'] or 'absent' in name:
                    if 'ABSENT' in added:
                        continue
                    added.add('ABSENT')
                    filtered_lines.append(line)
                    if rem_cash_deduction_hrs > 0.01:
                        lat_type = self.env['hr.work.entry.type'].sudo().search([('code', 'in', ['LAT', 'LATENESS'])], limit=1)
                        filtered_lines.append({
                            'name': 'Lateness / Undertime Deduction',
                            'code': 'LATENESS',
                            'work_entry_type_id': lat_type.id if lat_type else False,
                            'number_of_hours': rem_cash_deduction_hrs,
                            'number_of_days': 0.0,
                            'amount': round(rem_cash_deduction_hrs * hourly_rate, 3),
                            'sequence': 26,
                        })
                else:
                    line_key = (code, line.get('work_entry_type_id'))
                    if line_key in added:
                        continue
                    added.add(line_key)
                    filtered_lines.append(line)

            if 'ATTENDANCE' not in added and final_attendance_days > 0.01:
                att_type = self.env['hr.work.entry.type'].sudo().search([('code', 'in', ['WORK100', 'ATTENDANCE'])], limit=1)
                filtered_lines.append({
                    'name': 'Attendance',
                    'code': 'WORK100',
                    'work_entry_type_id': att_type.id if att_type else False,
                    'number_of_hours': total_reg_hrs if total_reg_hrs > 0 else round(final_attendance_days * 8.0, 2),
                    'number_of_days': final_attendance_days,
                    'amount': round((total_reg_hrs if total_reg_hrs > 0 else final_attendance_days * 8.0) * hourly_rate, 3),
                    'sequence': 1,
                })

            res = filtered_lines
        return res

    def _apply_termination_clearance_inputs(self):
        """Populates CLEAR_EXTRA, CLEAR_ANNUAL, CLEAR_PTO for termination clearance payslips."""
        input_model = self.env["hr.payslip.input"]
        for slip in self:
            is_term = getattr(slip, 'termination_clearance', False) or (slip.struct_id and 'termination' in slip.struct_id.name.lower())
            if not is_term or not slip.employee_id:
                continue

            emp = slip.employee_id
            w = emp.wage or 0.0
            hourly_rate = w / 240.0
            daily_rate = w / 30.0

            # 1. CLEAR_EXTRA
            ot_hrs = max(0.0, round(slip.remaining_extra_hours_balance, 2))
            ot_amount = round(ot_hrs * hourly_rate, 3)
            ot_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'CLEAR_EXTRA')], limit=1)
            if ot_type:
                ot_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == ot_type)
                if ot_line:
                    ot_line.write({'quantity': ot_hrs, 'amount': ot_amount})
                elif slip.id:
                    input_model.create({'payslip_id': slip.id, 'input_type_id': ot_type.id, 'quantity': ot_hrs, 'amount': ot_amount})

            # 2. CLEAR_ANNUAL & CLEAR_PTO
            annual_days = 0.0
            pto_days = 0.0
            if 'hr.leave.allocation' in self.env:
                allocs = self.env['hr.leave.allocation'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'validate'),
                ])
                for a in allocs:
                    name = (a.holiday_status_id.name or '').lower()
                    rem = getattr(a, 'number_of_days_display', 0.0) or getattr(a, 'number_of_days', 0.0) or 0.0
                    taken = getattr(a, 'leaves_taken', 0.0) or 0.0
                    net_days = max(0.0, rem - taken)
                    if 'annual' in name or 'سنوي' in name:
                        annual_days += net_days
                    elif 'paid time off' in name or 'مدفوع' in name or 'pto' in name:
                        pto_days += net_days

            # Subtract Step 2 lateness covered by annual leave
            post_annual_days = max(0.0, round(annual_days - ((slip.lateness_covered_by_annual_leave or 0.0) / 8.0), 4))
            ann_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'CLEAR_ANNUAL')], limit=1)
            if ann_type:
                ann_amount = round(post_annual_days * daily_rate, 3)
                ann_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == ann_type)
                if ann_line:
                    ann_line.write({'quantity': post_annual_days, 'amount': ann_amount})
                elif slip.id:
                    input_model.create({'payslip_id': slip.id, 'input_type_id': ann_type.id, 'quantity': post_annual_days, 'amount': ann_amount})

            pto_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'CLEAR_PTO')], limit=1)
            if pto_type:
                pto_amount = round(pto_days * daily_rate, 3)
                pto_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == pto_type)
                if pto_line:
                    pto_line.write({'quantity': pto_days, 'amount': pto_amount})
                elif slip.id:
                    input_model.create({'payslip_id': slip.id, 'input_type_id': pto_type.id, 'quantity': pto_days, 'amount': pto_amount})

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

    def unlink(self):
        self._revert_reconciliation_settlements()
        return super().unlink()

    def _sync_reconciliation_settlements(self):
        """Synchronizes remaining extra hours to allocation and employee profile."""
        LeaveType = self.env['hr.leave.type'].sudo() if 'hr.leave.type' in self.env else None
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None

        for payslip in self:
            if not payslip.employee_id or not payslip.date_to:
                continue

            emp = payslip.employee_id
            month_str = payslip.date_to.strftime('%B %Y')
            target_hours = round(payslip.remaining_extra_hours_balance or 0.0, 2)
            target_days = round(target_hours / 8.0, 4)

            # Sync employee profile fields
            for fname in ['total_overtime', 'total_extra_hours', 'extra_hours_balance', 'overtime_balance']:
                if fname in emp._fields:
                    try:
                        emp.sudo().write({fname: target_hours})
                    except Exception:
                        pass

            # Update Extra Hours Allocation
            if LeaveType and Allocation:
                extra_types = LeaveType.search(['|', '|', ('name', '=', 'Extra Hours'), ('name', 'ilike', 'Extra Hours'), ('name', 'ilike', 'إضافي')])
                extra_type = extra_types[0] if extra_types else None
                if extra_type:
                    alloc_name = f"Extra Hours Reconciliation: {month_str} - {emp.name}"
                    existing_alloc = Allocation.search([
                        ('employee_id', '=', emp.id),
                        ('holiday_status_id', '=', extra_type.id),
                        ('name', '=', alloc_name),
                    ], limit=1)

                    if existing_alloc:
                        existing_alloc.write({'number_of_days': target_days})
                    elif target_days > 0.001:
                        new_alloc = Allocation.create({
                            'name': alloc_name,
                            'employee_id': emp.id,
                            'holiday_status_id': extra_type.id,
                            'number_of_days': target_days,
                            'date_from': payslip.date_from,
                        })
                        if hasattr(new_alloc, 'action_approve'):
                            try:
                                new_alloc.action_approve()
                            except Exception:
                                pass
                        new_alloc.write({'state': 'validate'})
                        payslip.write({'extra_hours_allocated_days': target_days})

    def _revert_reconciliation_settlements(self):
        """Restores pre-reconciliation state cleanly."""
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None

        for payslip in self:
            if not getattr(payslip, 'is_reconciled', False) and payslip.state in ['draft', 'verify']:
                continue

            emp = payslip.employee_id
            if emp:
                pre_recon_ot = round(payslip.total_extra_hours_available or 0.0, 2)
                for fname in ['total_overtime', 'total_extra_hours', 'extra_hours_balance', 'overtime_balance']:
                    if fname in emp._fields:
                        try:
                            emp.sudo().write({fname: pre_recon_ot})
                        except Exception:
                            pass

            if Allocation and payslip.date_to and emp:
                month_str = payslip.date_to.strftime('%B %Y')
                alloc_name = f"Extra Hours Reconciliation: {month_str} - {emp.name}"
                month_allocs = Allocation.search([
                    ('employee_id', '=', emp.id),
                    ('name', '=', alloc_name),
                ])
                if month_allocs:
                    month_allocs.write({'state': 'confirm'})
                    month_allocs.unlink()

            payslip.write({'is_reconciled': False, 'extra_hours_allocated_days': 0.0})

    def _action_create_account_move(self):
        """Group payslips by company before creating accounting entries."""
        slips_by_company = defaultdict(lambda: self.env['hr.payslip'])
        for slip in self:
            slips_by_company[slip.company_id] |= slip
        for company, slips in slips_by_company.items():
            super(HrPayslip, slips)._action_create_account_move()
