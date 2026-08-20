# -*- coding: utf-8 -*-

import datetime
import logging
from collections import defaultdict
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

    # 3-Step Lateness Settlement Audit Breakdown Fields
    lateness_covered_by_extra_hours = fields.Float(
        string="Step 1: Lateness Deducted from Extra Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Step 1: Lateness hours covered using total available Extra Hours Balance."
    )
    lateness_covered_by_annual_leave = fields.Float(
        string="Step 2a: Lateness Deducted from Annual Leave",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Step 2a: Lateness hours covered using available Annual Leave balance."
    )
    lateness_covered_by_paid_time_off = fields.Float(
        string="Step 2b: Lateness Deducted from Paid Time Off",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Step 2b: Lateness hours covered using available Paid Time Off balance when Annual Leave is exhausted."
    )
    undertime_cash_deduction_hours = fields.Float(
        string="Step 3: Remaining Lateness Deducted from Cash",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Step 3: Final remaining lateness hours deducted from monthly cash salary."
    )

    # Legacy field aliases for view compatibility
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

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        valid_slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to)
        if not valid_slips:
            for payslip in self:
                payslip.attendance_gross_overtime = 0.0
                payslip.attendance_gross_undertime = 0.0
                payslip.attendance_net_reconciled = 0.0
                payslip.total_extra_hours_available = 0.0
                payslip.lateness_covered_by_extra_hours = 0.0
                payslip.lateness_covered_by_annual_leave = 0.0
                payslip.lateness_covered_by_paid_time_off = 0.0
                payslip.undertime_cash_deduction_hours = 0.0
            return

        # 1. Bulk Rest Day Conversion
        valid_slips._convert_flexible_rest_days_to_ars()

        emp_ids = valid_slips.mapped('employee_id').ids
        min_date = min(valid_slips.mapped('date_from'))
        max_date = max(valid_slips.mapped('date_to'))

        # Bulk Pre-fetch 1: Attendances for all employees in batch
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', emp_ids),
            ('check_in', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
            ('check_in', '<=', datetime.datetime.combine(max_date, datetime.time.max))
        ])
        att_by_emp = defaultdict(list)
        for att in attendances:
            att_by_emp[att.employee_id.id].append(att)

        # Bulk Pre-fetch 2: Banked extra hours
        banked_extra_by_emp = defaultdict(float)
        if 'hr.attendance.overtime.line' in self.env:
            ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', '<', min_date),
                ('compensable_as_leave', '=', True),
                ('status', '=', 'approved'),
            ])
            for line in ot_lines:
                banked_extra_by_emp[line.employee_id.id] += line.duration

        # Bulk Pre-fetch 3: Leave allocations & taken leaves (Extra Hours, Annual Leave, Paid Time Off)
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
                # Exclude monthly overtime allocations for the current batch so prior balance is isolated
                if 'Monthly Overtime Earned' in (alloc.name or ''):
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

        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                payslip.attendance_gross_overtime = 0.0
                payslip.attendance_gross_undertime = 0.0
                payslip.attendance_net_reconciled = 0.0
                payslip.total_extra_hours_available = 0.0
                payslip.lateness_covered_by_extra_hours = 0.0
                payslip.lateness_covered_by_annual_leave = 0.0
                payslip.lateness_covered_by_paid_time_off = 0.0
                payslip.undertime_cash_deduction_hours = 0.0
                continue

            emp_id = payslip.employee_id.id
            emp_attendances = [
                att for att in att_by_emp.get(emp_id, [])
                if payslip.date_from <= att.check_in.date() <= payslip.date_to
            ]

            # In-memory variance calculation (0 DB queries per slip)
            daily_hours = defaultdict(float)
            for att in emp_attendances:
                daily_hours[att.check_in.date()] += att.worked_hours

            total_days_in_month = (payslip.date_to - payslip.date_from).days + 1
            target_work_days = total_days_in_month - (total_days_in_month // 7)

            break_hrs = payslip.employee_id._get_lunch_break_duration() if payslip.employee_id else 1.0
            min_ot_threshold = 0.75
            min_lateness_threshold = 0.25

            total_ot = 0.0
            total_undertime = 0.0
            worked_days_count = len(daily_hours)

            # Method 2: Earn 1 Rest Day for every 6 Worked Days
            allowed_rest_days = worked_days_count // 6

            for att_date, raw_hrs in daily_hours.items():
                if raw_hrs >= 6.0:
                    net_hrs = max(0.0, raw_hrs - break_hrs)
                elif raw_hrs > 4.0:
                    net_hrs = max(0.0, raw_hrs - (break_hrs / 2.0))
                else:
                    net_hrs = raw_hrs

                standard_target = 8.0
                if net_hrs > standard_target:
                    ot_excess = net_hrs - standard_target
                    if ot_excess >= min_ot_threshold:
                        # 125% Overtime multiplier (1h overtime = 1.25h extra hours)
                        total_ot += (ot_excess * 1.25)
                elif net_hrs < standard_target:
                    shortfall = standard_target - net_hrs
                    if shortfall > min_lateness_threshold:
                        total_undertime += shortfall

            if worked_days_count > target_work_days:
                extra_worked_days = worked_days_count - target_work_days
                total_ot += (extra_worked_days * 8.0 * 1.25)
            else:
                unworked_days = total_days_in_month - worked_days_count
                if unworked_days > allowed_rest_days:
                    excess_unworked_days = unworked_days - allowed_rest_days
                    total_undertime += (excess_unworked_days * 8.0)

            gross_ot = round(total_ot, 2)
            gross_ut = round(total_undertime, 2)

            payslip.attendance_gross_overtime = gross_ot
            payslip.attendance_gross_undertime = gross_ut
            payslip.attendance_net_reconciled = round(gross_ot - gross_ut, 2)

            prior_alloc_extra = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in extra_type_ids))
            prior_ot_line_extra = round(banked_extra_by_emp.get(emp_id, 0.0), 2)
            prev_extra_hours = max(prior_alloc_extra, prior_ot_line_extra)

            total_extra_avail = round(prev_extra_hours + gross_ot, 2)
            payslip.total_extra_hours_available = total_extra_avail

            lateness = gross_ut

            # STEP 1: Deduct lateness from Extra Hours
            covered_extra = round(min(lateness, total_extra_avail), 2)
            rem_lateness = round(lateness - covered_extra, 2)

            # STEP 2a: Deduct remaining lateness from Annual Leave
            covered_annual_leave = 0.0
            if rem_lateness > 0.01:
                annual_leave_avail = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in annual_type_ids))
                covered_annual_leave = round(min(rem_lateness, annual_leave_avail), 2)
                rem_lateness = round(rem_lateness - covered_annual_leave, 2)

            # STEP 2b: Deduct remaining lateness from Paid Time Off
            covered_paid_time_off = 0.0
            if rem_lateness > 0.01:
                paid_time_off_avail = max(0.0, sum(alloc_hours_by_emp_type.get((emp_id, tid), 0.0) for tid in pto_type_ids))
                covered_paid_time_off = round(min(rem_lateness, paid_time_off_avail), 2)
                rem_lateness = round(rem_lateness - covered_paid_time_off, 2)

            if rem_lateness < 0.01:
                rem_lateness = 0.0

            payslip.lateness_covered_by_extra_hours = covered_extra
            payslip.lateness_covered_by_annual_leave = covered_annual_leave
            payslip.lateness_covered_by_paid_time_off = covered_paid_time_off
            payslip.undertime_cash_deduction_hours = rem_lateness

    def compute_sheet(self):
        # 1. Run full reconciliation ONLY for payslips that have not been reconciled yet
        unreconciled_slips = self.filtered(lambda s: not s.is_reconciled)
        _logger.info(
            "Factory ExtraHours DEBUG compute_sheet: slips=%s unreconciled=%s reconciled_flags=%s",
            [(s.id, s.employee_id.name, s.is_reconciled) for s in self],
            unreconciled_slips.ids,
            {s.id: s.is_reconciled for s in self},
        )
        if unreconciled_slips:
            for payslip in unreconciled_slips:
                if payslip.employee_id and payslip.date_from and payslip.date_to:
                    if hasattr(payslip.employee_id, '_create_absent_work_entries_for_period'):
                        payslip.employee_id._create_absent_work_entries_for_period(payslip.date_from, payslip.date_to)

            unreconciled_slips._convert_flexible_rest_days_to_ars()

            # Force refresh worked_days_line_ids so the payslip Worked Days tab instantly updates
            for payslip in unreconciled_slips:
                if payslip.state == 'draft':
                    worked_days_vals = payslip._get_worked_day_lines()
                    payslip.worked_days_line_ids.unlink()
                    payslip.write({'worked_days_line_ids': [(0, 0, val) for val in worked_days_vals]})

            unreconciled_slips._compute_attendance_reconciliation_fields()
            unreconciled_slips._sync_reconciliation_settlements()
            unreconciled_slips.write({'is_reconciled': True})
        else:
            # Re-compute totals and refresh Extra Hours Time Off card on every Compute Sheet
            self._compute_attendance_reconciliation_fields()
            self._sync_extra_hours_time_off_balance()

        # 2. Always compute salary rules so newly added salary inputs/adjustments are calculated!
        res = super().compute_sheet()
        return res

    def action_payslip_done(self):
        res = super().action_payslip_done()
        self._sync_reconciliation_settlements()
        return res

    def action_payslip_draft(self):
        self._revert_reconciliation_settlements()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        res = super().action_payslip_cancel()
        self._revert_reconciliation_settlements()
        return res

    def action_cancel(self):
        res = super().action_cancel() if hasattr(super(), 'action_cancel') else True
        self._revert_reconciliation_settlements()
        return res

    def unlink(self):
        self._revert_reconciliation_settlements()
        return super().unlink()

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'cancel':
            self._revert_reconciliation_settlements()
        return res

    def _get_worked_day_lines(self, *args, **kwargs):
        """
        Harmonizes Odoo's native Worked Days tab lines with our Reconciliation Engine:
        1. Break Deduction: Deducts lunch break per shift from the Attendance line.
        2. Overtime: Matches net remaining extra hours after Step 1 lateness settlement.
        3. Absent / Lateness Cash Deduction: ONLY includes cash deduction for Step 3 remaining lateness (undertime_cash_deduction_hours).
           If lateness was settled via Annual Leave (Step 2), NO cash deduction is made from salary!
        4. Excludes settlement leave entries from the Worked Days table.
        """
        res = super()._get_worked_day_lines(*args, **kwargs)
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue

            emp = payslip.employee_id
            break_hrs = emp._get_lunch_break_duration() if emp else 1.0
            w = emp.wage if emp else 0.0
            hourly_rate = w / 240.0

            # Count worked shifts in this period
            attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', emp.id),
                ('check_in', '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                ('check_in', '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max))
            ])
            worked_shifts_count = len(set(att.check_in.date() for att in attendances))

            net_extra_hrs = round(payslip.attendance_gross_overtime - payslip.lateness_covered_by_extra_hours, 2)
            rem_cash_deduction_hrs = round(payslip.undertime_cash_deduction_hours, 2)

            filtered_lines = []
            for line in res:
                code = (line.get('code') or '').strip()
                work_entry_type = self.env['hr.work.entry.type'].browse(line.get('work_entry_type_id')) if line.get('work_entry_type_id') else None
                we_name = (work_entry_type.name or '').lower() if work_entry_type else ''
                line_name = (line.get('name') or '').lower()

                # Filter out settlement leaves so they don't appear as fake vacations
                if 'settlement' in line_name or 'lateness coverage' in line_name or 'monthly lateness' in line_name:
                    continue

                # 1. Attendance Line Break Deduction: Net Paid Working Hours = Raw Hours - (Shifts * Break)
                if code in ['WORK100', 'A', 'ATTENDANCE'] or 'attendance' in we_name:
                    raw_hours = line.get('number_of_hours', 0.0)
                    total_break_deduction = worked_shifts_count * break_hrs
                    if raw_hours > total_break_deduction and total_break_deduction > 0:
                        net_work_hours = round(raw_hours - total_break_deduction, 2)
                        line['number_of_hours'] = net_work_hours
                        line['number_of_days'] = round(net_work_hours / 8.0, 2)
                        line['amount'] = round(net_work_hours * hourly_rate, 3)
                    filtered_lines.append(line)

                # 2. Overtime Line
                elif code in ['OVERTIME', 'EXTRA', 'OUT'] or 'overtime' in we_name or 'extra' in we_name:
                    if net_extra_hrs > 0.01:
                        line['number_of_hours'] = net_extra_hrs
                        line['number_of_days'] = round(net_extra_hrs / 8.0, 2)
                        line['amount'] = round(net_extra_hrs * hourly_rate, 3)
                        filtered_lines.append(line)

                # 3. Absent / Unpaid Deduction Line: ONLY include if Step 3 Cash Deduction > 0!
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
        """
        Automatic Flexible Rest Day Conversion (Batch Optimized for 500+ employees):
        Converts 'Absent' (ABS / ABSENT) work entries on unworked rest days to 'Rest Day' (ARS)
        up to the earned rest day quota (Method 2: 1 Rest Day earned per 6 Worked Days).
        Safely handles validated work entries without raising Invalid Operation errors.
        """
        if not self:
            return

        valid_slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to)
        if not valid_slips:
            return

        rest_type = False
        if 'hr.work.entry' in self.env:
            rest_type = self.env['hr.work.entry.type'].sudo().search([
                '|', ('code', '=', 'ARS'), ('name', 'ilike', 'Rest')
            ], limit=1)

        if not rest_type:
            return

        emp_ids = valid_slips.mapped('employee_id').ids
        min_date = min(valid_slips.mapped('date_from'))
        max_date = max(valid_slips.mapped('date_to'))

        # Bulk Query 1: Attendances for all employees
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', emp_ids),
            ('check_in', '>=', datetime.datetime.combine(min_date, datetime.time.min)),
            ('check_in', '<=', datetime.datetime.combine(max_date, datetime.time.max))
        ])
        worked_dates_by_emp = defaultdict(set)
        for att in attendances:
            worked_dates_by_emp[att.employee_id.id].add(att.check_in.date())

        # Bulk Query 2: Work entries for all employees
        WorkEntry = self.env['hr.work.entry'].sudo()
        we_fields = WorkEntry._fields
        start_field = next((c for c in ['date_start', 'date_from', 'start_datetime', 'date'] if c in we_fields), None)
        stop_field = next((c for c in ['date_stop', 'date_to', 'end_datetime', 'date'] if c in we_fields), None)

        if not start_field or not stop_field:
            return

        work_entries = WorkEntry.search([
            ('employee_id', 'in', emp_ids),
            (start_field, '>=', datetime.datetime.combine(min_date, datetime.time.min)),
            (stop_field, '<=', datetime.datetime.combine(max_date, datetime.time.max))
        ]).sorted(start_field)

        we_by_emp = defaultdict(list)
        for we in work_entries:
            we_by_emp[we.employee_id.id].append(we)

        for payslip in valid_slips:
            try:
                emp_id = payslip.employee_id.id
                slip_start = datetime.datetime.combine(payslip.date_from, datetime.time.min)
                slip_end = datetime.datetime.combine(payslip.date_to, datetime.time.max)

                slip_worked_dates = set(
                    d for d in worked_dates_by_emp.get(emp_id, set())
                    if payslip.date_from <= d <= payslip.date_to
                )

                emp_work_entries = [
                    we for we in we_by_emp.get(emp_id, [])
                    if getattr(we, start_field) and getattr(we, stop_field) and
                    getattr(we, start_field) >= slip_start and getattr(we, stop_field) <= slip_end
                ]

                for we in emp_work_entries:
                    code = (we.work_entry_type_id.code or '').strip()
                    name = (we.work_entry_type_id.name or '').lower()
                    if not we.work_entry_type_id.is_leave and code not in ['LEAVE500', 'UNPAID', 'ABSENT', 'ABS'] and 'absent' not in name:
                        start_val = getattr(we, start_field, None)
                        if start_val:
                            we_date = start_val.date() if isinstance(start_val, datetime.datetime) else (start_val if isinstance(start_val, datetime.date) else None)
                            if we_date:
                                slip_worked_dates.add(we_date)

                worked_days_count = len(slip_worked_dates)
                allowed_rest_days = worked_days_count // 6

                converted_count = 0
                for we in emp_work_entries:
                    start_val = getattr(we, start_field, None)
                    if not start_val:
                        continue
                    we_date = start_val.date() if isinstance(start_val, datetime.datetime) else (start_val if isinstance(start_val, datetime.date) else None)
                    if we_date:
                        code = (we.work_entry_type_id.code or '').strip()
                        name = (we.work_entry_type_id.name or '').lower()
                        if code in ['LEAVE500', 'UNPAID', 'ABSENT', 'ABS'] or 'absent' in name:
                            if converted_count < allowed_rest_days:
                                if hasattr(we, 'state') and we.state == 'validated':
                                    we.sudo().write({'state': 'draft'})
                                we.sudo().write({'work_entry_type_id': rest_type.id})
                                converted_count += 1
            except Exception:
                pass

    def _create_or_update_settlement_leave(self, leave_type_name, hours, leave_desc):
        """
        Creates validated hr.leave settlement records per absent date (e.g. Day 19, Day 31)
        and supports fractional hours (less than a full day) using hourly time off.
        Directly links to the active allocation to reduce balance without altering calendar ABS entries.
        """
        self.ensure_one()
        Leave = self.env['hr.leave'].sudo()
        LeaveType = self.env['hr.leave.type'].sudo()

        if leave_type_name == 'Extra Hours':
            leave_types = LeaveType.search([
                '|', '|',
                ('name', '=', 'Extra Hours'),
                ('name', 'ilike', 'Extra Hours'),
                ('name', 'ilike', 'إضافي')
            ])
        elif leave_type_name == 'Annual Leave':
            leave_types = LeaveType.search([
                '|', '|',
                ('name', '=', 'Annual Leave'),
                ('name', 'ilike', 'Annual Leave'),
                ('name', 'ilike', 'سنوي')
            ])
        elif leave_type_name == 'Paid Time Off':
            leave_types = LeaveType.search([
                '|', '|',
                ('name', '=', 'Paid Time Off'),
                ('name', 'ilike', 'Paid Time Off'),
                ('name', 'ilike', 'مدفوع')
            ])
        else:
            leave_types = LeaveType.search([('name', '=', leave_type_name)])

        leave_type = leave_types[0] if leave_types else None
        if not leave_type:
            return

        # 1. Clean up previously generated settlement leaves for this leave type in this payslip period
        prev_settlement_leaves = Leave.search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', leave_type.id),
            ('request_date_from', '>=', self.date_from),
            ('request_date_to', '<=', self.date_to),
            ('name', 'ilike', 'Lateness Settlement'),
        ])
        if prev_settlement_leaves:
            prev_settlement_leaves.unlink()

        if hours <= 0.01:
            return

        # 2. Find the active validated allocation
        alloc = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
        ], order='date_to desc, id desc', limit=1)

        # 3. Find candidate absent / unpunched dates in this payslip period
        absent_dates = []
        if 'hr.work.entry' in self.env:
            WorkEntry = self.env['hr.work.entry'].sudo()
            we_fields = WorkEntry._fields
            start_field = next((c for c in ['date_start', 'date_from', 'start_datetime', 'date'] if c in we_fields), None)
            stop_field = next((c for c in ['date_stop', 'date_to', 'end_datetime', 'date'] if c in we_fields), None)
            if start_field and stop_field:
                domain = [
                    ('employee_id', '=', self.employee_id.id),
                    (start_field, '>=', datetime.datetime.combine(self.date_from, datetime.time.min)),
                    (stop_field, '<=', datetime.datetime.combine(self.date_to, datetime.time.max)),
                    ('work_entry_type_id.code', 'in', ['ABS', 'ABSENT']),
                ]
                absent_entries = WorkEntry.search(domain).sorted(start_field)
                for we in absent_entries:
                    start_val = getattr(we, start_field, None)
                    d = start_val.date() if isinstance(start_val, datetime.datetime) else (start_val if isinstance(start_val, datetime.date) else None)
                    if d and d not in absent_dates:
                        absent_dates.append(d)

        # If no absent work entries found, fallback to month-end date
        if not absent_dates:
            absent_dates = [self.date_to]

        ctx_leave = Leave.with_context(
            employee_id=self.employee_id.id,
            mail_create_nolog=True,
            mail_notrack=True,
            tracking_disable=True,
            leave_skip_state_check=True,
            leave_skip_work_entries=True,
            no_work_entry=True,
        )

        remaining_hours = hours
        absent_date_idx = 0

        # 4. Create 1-day settlement records for full days (8.0h chunks) on exact absent dates
        while remaining_hours >= 7.99:
            target_date = absent_dates[absent_date_idx] if absent_date_idx < len(absent_dates) else self.date_to
            absent_date_idx += 1

            dt_start = datetime.datetime.combine(target_date, datetime.time(8, 0, 0))
            dt_stop = datetime.datetime.combine(target_date, datetime.time(17, 0, 0))

            full_name = f"Lateness Settlement ({leave_type_name}) - {target_date.strftime('%d/%m/%Y')}"
            leave_vals = {
                'name': full_name,
                'employee_id': self.employee_id.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': target_date,
                'request_date_to': target_date,
                'date_from': dt_start,
                'date_to': dt_stop,
                'number_of_days': 1.0,
                'state': 'validate',
            }
            if 'number_of_days_display' in Leave._fields:
                leave_vals['number_of_days_display'] = 1.0
            if 'number_of_hours' in Leave._fields:
                leave_vals['number_of_hours'] = 8.0
            if 'number_of_hours_display' in Leave._fields:
                leave_vals['number_of_hours_display'] = 8.0
            if alloc:
                if 'holiday_allocation_id' in Leave._fields:
                    leave_vals['holiday_allocation_id'] = alloc.id
                elif 'allocation_id' in Leave._fields:
                    leave_vals['allocation_id'] = alloc.id

            try:
                new_leave = ctx_leave.create(leave_vals)
                new_leave.sudo().write({'state': 'validate'})
                if 'hr.work.entry' in self.env:
                    we_model = self.env['hr.work.entry'].sudo()
                    if 'leave_id' in we_model._fields:
                        generated_we = we_model.search([('leave_id', '=', new_leave.id)])
                        if generated_we:
                            generated_we.unlink()
            except Exception:
                pass

            remaining_hours -= 8.0

        # 5. Create hourly settlement record for remaining fractional hours (< 8.0h, e.g. 2h)
        if remaining_hours > 0.01:
            target_date = absent_dates[absent_date_idx] if absent_date_idx < len(absent_dates) else self.date_to
            frac_hours = round(remaining_hours, 2)
            frac_days = round(frac_hours / 8.0, 4)

            dt_start = datetime.datetime.combine(target_date, datetime.time(8, 0, 0))
            dt_stop = dt_start + datetime.timedelta(hours=frac_hours)

            full_name = f"Lateness Settlement ({leave_type_name}) - {frac_hours}h ({target_date.strftime('%d/%m/%Y')})"
            leave_vals = {
                'name': full_name,
                'employee_id': self.employee_id.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': target_date,
                'request_date_to': target_date,
                'request_unit_hours': True,
                'request_hour_from': 8.0,
                'request_hour_to': 8.0 + frac_hours,
                'date_from': dt_start,
                'date_to': dt_stop,
                'number_of_days': frac_days,
                'state': 'validate',
            }
            if 'number_of_days_display' in Leave._fields:
                leave_vals['number_of_days_display'] = frac_days
            if 'number_of_hours' in Leave._fields:
                leave_vals['number_of_hours'] = frac_hours
            if 'number_of_hours_display' in Leave._fields:
                leave_vals['number_of_hours_display'] = frac_hours
            if alloc:
                if 'holiday_allocation_id' in Leave._fields:
                    leave_vals['holiday_allocation_id'] = alloc.id
                elif 'allocation_id' in Leave._fields:
                    leave_vals['allocation_id'] = alloc.id

            try:
                new_leave = ctx_leave.create(leave_vals)
                new_leave.sudo().write({'state': 'validate'})
                if 'hr.work.entry' in self.env:
                    we_model = self.env['hr.work.entry'].sudo()
                    if 'leave_id' in we_model._fields:
                        generated_we = we_model.search([('leave_id', '=', new_leave.id)])
                        if generated_we:
                            generated_we.unlink()
            except Exception:
                pass

    def _sync_extra_hours_time_off_balance(self):
        """
        Sync employee Time Off "Extra Hours" card with payslip reconciliation.

        Odoo 19 reads Extra Hours from hr.attendance.overtime.line
        (compensable_as_leave + approved), NOT from leave allocations.
        Creating Extra Hours allocations with overtime_deductible cancels the
        overtime credit on the dashboard — so we only maintain overtime lines.

        Target available hours =
            total_extra_hours_available - lateness_covered_by_extra_hours
        (e.g. 10:30 when previous 08:00 + monthly OT 02:30 and no Step-1 lateness).
        """
        OvertimeLine = self.env['hr.attendance.overtime.line'].sudo() if 'hr.attendance.overtime.line' in self.env else None
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None
        Leave = self.env['hr.leave'].sudo() if 'hr.leave' in self.env else None
        LeaveType = self.env['hr.leave.type'].sudo() if 'hr.leave.type' in self.env else None

        _logger.info(
            "Factory ExtraHours DEBUG sync START payslips=%s OvertimeLine_model=%s",
            self.ids,
            bool(OvertimeLine),
        )
        if not OvertimeLine:
            _logger.warning("Factory ExtraHours DEBUG abort: hr.attendance.overtime.line model missing")
            return

        for payslip in self:
            if not payslip.employee_id or not payslip.date_to:
                _logger.info(
                    "Factory ExtraHours DEBUG skip payslip id=%s emp=%s date_to=%s",
                    payslip.id,
                    payslip.employee_id.id if payslip.employee_id else None,
                    payslip.date_to,
                )
                continue

            employee = payslip.employee_id
            target_hours = round(
                (payslip.total_extra_hours_available or 0.0)
                - (payslip.lateness_covered_by_extra_hours or 0.0),
                2,
            )
            _logger.info(
                "Factory ExtraHours DEBUG payslip=%s emp=%s(%s) "
                "total_extra=%s step1_lateness=%s gross_ot=%s TARGET=%s is_reconciled=%s",
                payslip.id,
                employee.name,
                employee.id,
                payslip.total_extra_hours_available,
                payslip.lateness_covered_by_extra_hours,
                payslip.attendance_gross_overtime,
                target_hours,
                payslip.is_reconciled,
            )

            # Remove Extra Hours allocations that cancel overtime on the dashboard
            # (any name: Monthly Overtime Earned / Extra Hours Reconciliation / etc.)
            if Allocation and LeaveType:
                extra_types = LeaveType.search([
                    '|', '|', '|',
                    ('name', '=', 'Extra Hours'),
                    ('name', 'ilike', 'Extra Hours'),
                    ('name', 'ilike', 'إضافي'),
                    ('overtime_deductible', '=', True),
                ]) if 'overtime_deductible' in LeaveType._fields else LeaveType.search([
                    '|', '|',
                    ('name', '=', 'Extra Hours'),
                    ('name', 'ilike', 'Extra Hours'),
                    ('name', 'ilike', 'إضافي'),
                ])
                alloc_domain = [('employee_id', '=', employee.id)]
                if extra_types:
                    alloc_domain.append(('holiday_status_id', 'in', extra_types.ids))
                else:
                    alloc_domain.extend(['|', ('name', 'ilike', 'Overtime Earned'), ('name', 'ilike', 'Extra Hours Reconciliation')])
                all_extra_allocs = Allocation.search(alloc_domain)
                _logger.info(
                    "Factory ExtraHours DEBUG allocations before cleanup emp=%s count=%s details=%s",
                    employee.id,
                    len(all_extra_allocs),
                    [
                        (
                            a.id,
                            a.name,
                            a.holiday_status_id.name,
                            a.number_of_days,
                            getattr(a, 'number_of_hours_display', None) or getattr(a, 'number_of_hours', None),
                            a.state,
                        )
                        for a in all_extra_allocs
                    ],
                )
                if all_extra_allocs:
                    all_extra_allocs.unlink()
                    _logger.info("Factory ExtraHours DEBUG unlinked %s Extra Hours allocations", len(all_extra_allocs))

            # Extra Hours lateness is applied on the overtime line only (avoid double deduction)
            if Leave and LeaveType:
                extra_types = LeaveType.search([
                    '|', '|',
                    ('name', '=', 'Extra Hours'),
                    ('name', 'ilike', 'Extra Hours'),
                    ('name', 'ilike', 'إضافي'),
                ])
                if extra_types:
                    extra_settlements = Leave.search([
                        ('employee_id', '=', employee.id),
                        ('holiday_status_id', 'in', extra_types.ids),
                        ('request_date_from', '>=', payslip.date_from),
                        ('request_date_to', '<=', payslip.date_to),
                        ('name', 'ilike', 'Lateness Settlement'),
                    ])
                    _logger.info(
                        "Factory ExtraHours DEBUG Extra Hours settlement leaves=%s",
                        [(l.id, l.name, l.number_of_days, getattr(l, 'number_of_hours', None)) for l in extra_settlements],
                    )
                    if extra_settlements:
                        extra_settlements.unlink()

            all_ot_lines = OvertimeLine.search([
                ('employee_id', '=', employee.id),
                ('compensable_as_leave', '=', True),
            ])
            _logger.info(
                "Factory ExtraHours DEBUG ALL compensable OT lines emp=%s details=%s",
                employee.id,
                [
                    (l.id, l.date, l.duration, l.manual_duration, l.status, l.compensable_as_leave)
                    for l in all_ot_lines
                ],
            )

            reconciliation_lines = all_ot_lines.filtered(lambda l: l.date == payslip.date_to)
            existing_line = reconciliation_lines[:1]
            old_line_hours = 0.0
            if existing_line:
                old_line_hours = existing_line.manual_duration or existing_line.duration or 0.0

            current_available = 0.0
            if hasattr(employee, '_get_deductible_employee_overtime'):
                ot_map = employee._get_deductible_employee_overtime()
                current_available = ot_map.get(employee, 0.0) or 0.0
                _logger.info(
                    "Factory ExtraHours DEBUG deductible_map keys=%s current_available=%s",
                    [(k.id if hasattr(k, 'id') else k, v) for k, v in ot_map.items()],
                    current_available,
                )
            else:
                other_lines = OvertimeLine.search([
                    ('employee_id', '=', employee.id),
                    ('compensable_as_leave', '=', True),
                    ('status', '=', 'approved'),
                    ('id', 'not in', reconciliation_lines.ids),
                ])
                current_available = sum(other_lines.mapped('manual_duration') or other_lines.mapped('duration')) + old_line_hours
                _logger.info("Factory ExtraHours DEBUG fallback current_available=%s", current_available)

            base_without_line = round(current_available - old_line_hours, 2)
            line_hours = round(target_hours - base_without_line, 2)
            _logger.info(
                "Factory ExtraHours DEBUG calc emp=%s old_line=%s base_without=%s line_hours_needed=%s target=%s",
                employee.id,
                old_line_hours,
                base_without_line,
                line_hours,
                target_hours,
            )

            if abs(line_hours) < 0.01:
                if reconciliation_lines:
                    reconciliation_lines.unlink()
                    _logger.info("Factory ExtraHours DEBUG removed reconciliation lines (line_hours~0)")
                final_avail = 0.0
                if hasattr(employee, '_get_deductible_employee_overtime'):
                    final_avail = employee._get_deductible_employee_overtime().get(employee, 0.0) or 0.0
                _logger.info("Factory ExtraHours DEBUG AFTER(no write) available=%s expected=%s", final_avail, target_hours)
                continue

            vals = {
                'employee_id': employee.id,
                'date': payslip.date_to,
                'duration': line_hours,
                'manual_duration': line_hours,
                'compensable_as_leave': True,
                'status': 'approved',
            }
            try:
                if existing_line:
                    existing_line.write(vals)
                    (reconciliation_lines - existing_line).unlink()
                    _logger.info(
                        "Factory ExtraHours DEBUG UPDATED OT line id=%s vals=%s",
                        existing_line.id,
                        vals,
                    )
                else:
                    new_line = OvertimeLine.create(vals)
                    _logger.info(
                        "Factory ExtraHours DEBUG CREATED OT line id=%s vals=%s",
                        new_line.id,
                        vals,
                    )
            except Exception:
                _logger.exception(
                    "Factory ExtraHours DEBUG FAILED writing OT line emp=%s vals=%s",
                    employee.id,
                    vals,
                )
                continue

            final_avail = 0.0
            if hasattr(employee, '_get_deductible_employee_overtime'):
                final_avail = employee._get_deductible_employee_overtime().get(employee, 0.0) or 0.0
            _logger.info(
                "Factory ExtraHours DEBUG AFTER sync emp=%s available=%s expected_target=%s MATCH=%s",
                employee.id,
                final_avail,
                target_hours,
                abs(final_avail - target_hours) < 0.01,
            )

    def _sync_reconciliation_settlements(self):
        """
        1. Sync Extra Hours Time Off card via attendance overtime lines.
        2. Deduct Step 2a Annual Leave via approved hr.leave records.
        3. Deduct Step 2b Paid Time Off via approved hr.leave records.
        """
        for payslip in self:
            if not payslip.employee_id or not payslip.date_to:
                continue

            # Extra Hours dashboard (Odoo 19): overtime lines only
            payslip._sync_extra_hours_time_off_balance()

            # Annual Leave / PTO lateness settlement (real leave balances)
            payslip._create_or_update_settlement_leave(
                'Annual Leave',
                payslip.lateness_covered_by_annual_leave,
                'Lateness Settlement via Annual Leave'
            )
            payslip._create_or_update_settlement_leave(
                'Paid Time Off',
                payslip.lateness_covered_by_paid_time_off,
                'Lateness Settlement via Paid Time Off'
            )

    def _revert_reconciliation_settlements(self):
        """
        Reverses all Time Off settlement records (Extra Hours, Annual Leave, Paid Time Off),
        reverts credited monthly overtime allocations, and clears attendance overtime lines
        when the payslip is cancelled or set to draft.
        This immediately restores the balances back to the employee.
        """
        Leave = self.env['hr.leave'].sudo() if 'hr.leave' in self.env else None
        Allocation = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None
        OvertimeLine = self.env['hr.attendance.overtime.line'].sudo() if 'hr.attendance.overtime.line' in self.env else None

        for payslip in self:
            if not payslip.employee_id or not payslip.date_to:
                continue

            # Reset reconciliation flag so next compute can re-reconcile freshly
            payslip.write({'is_reconciled': False})

            # 1. Unlink/remove all settlement leaves created for this payslip's date range
            if Leave:
                settlement_leaves = Leave.search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('request_date_from', '>=', payslip.date_from),
                    ('request_date_to', '<=', payslip.date_to),
                    ('name', 'ilike', 'Lateness Settlement'),
                ])
                if settlement_leaves:
                    settlement_leaves.unlink()

            # 2. Revert Monthly Overtime Allocation if created for this payslip month
            if Allocation:
                month_str = payslip.date_to.strftime('%B %Y') if payslip.date_to else ''
                alloc_name = f"Monthly Overtime Earned - {month_str}"
                ot_allocs = Allocation.search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('name', '=', alloc_name),
                ])
                if ot_allocs:
                    ot_allocs.unlink()

            # 3. Revert Overtime line if created for this payslip date_to
            if OvertimeLine:
                ot_lines = OvertimeLine.search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('date', '=', payslip.date_to),
                    ('compensable_as_leave', '=', True),
                ])
                if ot_lines:
                    ot_lines.unlink()

    def _get_previous_extra_hours_balance(self):
        """
        Gets banked extra hours balance before the current payslip date_to.
        """
        self.ensure_one()
        if not self.employee_id:
            return 0.0
        if 'hr.attendance.overtime.line' in self.env:
            lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('date', '<', self.date_from),
                ('compensable_as_leave', '=', True),
                ('status', '=', 'approved'),
            ])
            return max(0.0, sum(lines.mapped('duration')))
        return 0.0

    def _get_available_leave_hours_by_type(self, type_category):
        """
        Gets available leave balance in hours for the given leave type category:
        - 'Annual Leave'
        - 'Paid Time Off'
        - 'Extra Hours'
        Converts allocations stored in Days to Hours (1 Day = 8.0 Hours).
        """
        self.ensure_one()
        if not self.employee_id:
            return 0.0

        LeaveType = self.env['hr.leave.type'].sudo()
        if type_category == 'Annual Leave':
            leave_types = LeaveType.search([
                '|', '|',
                ('name', '=', 'Annual Leave'),
                ('name', 'ilike', 'Annual Leave'),
                ('name', 'ilike', 'سنوي')
            ])
        elif type_category == 'Paid Time Off':
            leave_types = LeaveType.search([
                '|', '|',
                ('name', '=', 'Paid Time Off'),
                ('name', 'ilike', 'Paid Time Off'),
                ('name', 'ilike', 'مدفوع')
            ])
        elif type_category == 'Extra Hours':
            leave_types = LeaveType.search([
                '|', '|',
                ('name', '=', 'Extra Hours'),
                ('name', 'ilike', 'Extra Hours'),
                ('name', 'ilike', 'إضافي')
            ])
        else:
            leave_types = LeaveType.search([('name', '=', type_category)])

        if not leave_types:
            return 0.0

        total_allocated_hours = 0.0
        total_taken_hours = 0.0

        allocations = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id', 'in', leave_types.ids)
        ])

        for alloc in allocations:
            if hasattr(alloc, 'number_of_hours_display') and alloc.number_of_hours_display:
                total_allocated_hours += alloc.number_of_hours_display
            elif hasattr(alloc, 'number_of_days') and alloc.number_of_days:
                total_allocated_hours += (alloc.number_of_days * 8.0)
            elif hasattr(alloc, 'number_of_days_display') and alloc.number_of_days_display:
                total_allocated_hours += (alloc.number_of_days_display * 8.0)

        # Exclude settlement leaves created for this exact payslip window so recomputations don't double count
        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id', 'in', leave_types.ids),
            '!', '&', ('name', 'ilike', 'Monthly Lateness Settlement'), ('request_date_from', '=', self.date_to)
        ])

        for lve in leaves:
            if hasattr(lve, 'number_of_hours') and lve.number_of_hours:
                total_taken_hours += lve.number_of_hours
            elif hasattr(lve, 'number_of_days') and lve.number_of_days:
                total_taken_hours += (lve.number_of_days * 8.0)

        return max(0.0, total_allocated_hours - total_taken_hours)

    def _get_available_annual_leave_hours(self):
        """Legacy compatibility wrapper."""
        return self._get_available_leave_hours_by_type('Annual Leave')

    def _get_reconciled_attendance_variance(self):
        """
        Factory Flexible 6-Day Work Week & Monthly Rest Day Quota Reconciliation:
        - Ratio: 6 Working Days to 1 Rest Day.
        - Employees can stack/accumulate rest days freely (e.g. work 12 days straight, take 2 rest days off; work 26 days straight, take last 4 rest days off).
        - Multi-Location Break Deductions: Factory/Branch 1.0h break, Head Office 0.5h break for shifts >= 6.0h.
        - Overtime Threshold: Daily shift excess >= 45 minutes (0.75h).
        - Lateness Grace Period: Daily shift shortfalls <= 15 minutes (0.25h) are forgiven.
        """
        self.ensure_one()

        # 1. Fetch attendance records in payslip date window
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', datetime.datetime.combine(self.date_from, datetime.time.min)),
            ('check_in', '<=', datetime.datetime.combine(self.date_to, datetime.time.max))
        ])

        # 2. Group raw check-in hours by date
        daily_hours = defaultdict(float)
        for att in attendances:
            daily_hours[att.check_in.date()] += att.worked_hours

        # 3. Calculate Monthly Quota based on total days in payslip window
        total_days_in_month = (self.date_to - self.date_from).days + 1
        target_work_days = total_days_in_month - (total_days_in_month // 7)

        break_hrs = self.employee_id._get_lunch_break_duration() if self.employee_id else 1.0
        min_ot_threshold = 0.75         # 45 minutes Overtime threshold
        min_lateness_threshold = 0.25   # 15 minutes Lateness Grace Period

        total_ot = 0.0
        total_undertime = 0.0

        # Evaluate Daily Shift Variances for worked days
        worked_days_count = len(daily_hours)

        # Method 2: Earn 1 Rest Day for every 6 Worked Days
        allowed_rest_days = worked_days_count // 6

        for att_date, raw_hrs in daily_hours.items():
            # Apply break deduction rule according to employee location
            if raw_hrs >= 6.0:
                net_hrs = max(0.0, raw_hrs - break_hrs)
            elif raw_hrs > 4.0:
                net_hrs = max(0.0, raw_hrs - (break_hrs / 2.0))
            else:
                net_hrs = raw_hrs

            standard_target = 8.0  # Net Working Hours target per shift

            if net_hrs > standard_target:
                ot_excess = net_hrs - standard_target
                if ot_excess >= min_ot_threshold:
                    total_ot += ot_excess
            elif net_hrs < standard_target:
                shortfall = standard_target - net_hrs
                if shortfall > min_lateness_threshold:
                    total_undertime += shortfall

        # 4. Monthly Rest Day Quota Reconciliation
        if worked_days_count > target_work_days:
            # Employee worked extra days beyond monthly target -> Extra worked days count as Overtime!
            extra_worked_days = worked_days_count - target_work_days
            total_ot += (extra_worked_days * 8.0)
        else:
            unworked_days = total_days_in_month - worked_days_count
            if unworked_days > allowed_rest_days:
                # Employee took more off days than their rest day quota -> Excess unworked days count as Undertime
                excess_unworked_days = unworked_days - allowed_rest_days
                total_undertime += (excess_unworked_days * 8.0)

        return {
            'total_ot': total_ot,
            'total_undertime': total_undertime,
            'net_variance': total_ot - total_undertime
        }
