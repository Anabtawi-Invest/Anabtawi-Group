import datetime
from collections import defaultdict
from odoo import models, fields, api

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

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        for payslip in self:
            if payslip.employee_id and payslip.date_from and payslip.date_to:
                # Convert flexible rest days from Absent to Rest Day (ARS)
                payslip._convert_flexible_rest_days_to_ars()

                res = payslip._get_reconciled_attendance_variance()
                gross_ot = round(res.get('total_ot', 0.0), 2)
                gross_ut = round(res.get('total_undertime', 0.0), 2)

                payslip.attendance_gross_overtime = gross_ot
                payslip.attendance_gross_undertime = gross_ut
                payslip.attendance_net_reconciled = round(gross_ot - gross_ut, 2)

                # Get previous banked extra hours balance
                prev_extra_hours = round(payslip._get_previous_extra_hours_balance(), 2)
                total_extra_avail = round(prev_extra_hours + gross_ot, 2)
                payslip.total_extra_hours_available = total_extra_avail

                lateness = gross_ut

                # STEP 1: Deduct lateness from Total Available Extra Hours (Banked + New OT)
                covered_extra = round(min(lateness, total_extra_avail), 2)
                rem_lateness = round(lateness - covered_extra, 2)

                # STEP 2: Deduct remaining lateness from Annual Leave
                covered_leave = 0.0
                if rem_lateness > 0.01:
                    annual_leave_avail = round(payslip._get_available_annual_leave_hours(), 2)
                    covered_leave = round(min(rem_lateness, annual_leave_avail), 2)
                    rem_lateness = round(rem_lateness - covered_leave, 2)

                # Guard against floating-point micro fractions (< 0.01h)
                if rem_lateness < 0.01:
                    rem_lateness = 0.0

                # STEP 3: Remaining lateness goes to Monthly Cash Salary Deduction
                payslip.lateness_covered_by_extra_hours = covered_extra
                payslip.lateness_covered_by_annual_leave = covered_leave
                payslip.undertime_cash_deduction_hours = rem_lateness
            else:
                payslip.attendance_gross_overtime = 0.0
                payslip.attendance_gross_undertime = 0.0
                payslip.attendance_net_reconciled = 0.0
                payslip.total_extra_hours_available = 0.0
                payslip.lateness_covered_by_extra_hours = 0.0
                payslip.lateness_covered_by_annual_leave = 0.0
                payslip.undertime_cash_deduction_hours = 0.0

    def compute_sheet(self):
        for payslip in self:
            if payslip.employee_id and payslip.date_from and payslip.date_to:
                if hasattr(payslip.employee_id, '_create_absent_work_entries_for_period'):
                    payslip.employee_id._create_absent_work_entries_for_period(payslip.date_from, payslip.date_to)

        self._convert_flexible_rest_days_to_ars()

        # Force refresh worked_days_line_ids so the payslip Worked Days tab instantly updates
        for payslip in self:
            if payslip.state == 'draft':
                worked_days_vals = payslip._get_worked_day_lines()
                payslip.worked_days_line_ids.unlink()
                payslip.write({'worked_days_line_ids': [(0, 0, val) for val in worked_days_vals]})

        self._compute_attendance_reconciliation_fields()
        res = super().compute_sheet()
        self._sync_reconciliation_settlements()
        return res

    def action_payslip_draft(self):
        self._reset_reconciliation_settlements()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        self._reset_reconciliation_settlements()
        return super().action_payslip_cancel()

    def _reset_reconciliation_settlements(self):
        for payslip in self:
            if not payslip.employee_id:
                continue
            # Refuse and unlink generated lateness leaves to restore annual leave allocation balance
            if 'hr.leave' in self.env:
                gen_leaves = self.env['hr.leave'].sudo().search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('request_date_from', '<=', payslip.date_to),
                    ('request_date_to', '>=', payslip.date_from),
                    ('name', 'ilike', 'Lateness Settlement')
                ])
                for lve in gen_leaves:
                    if lve.state in ('confirm', 'validate1', 'validate', 'draft') and hasattr(lve, 'action_refuse'):
                        try:
                            lve.action_refuse()
                        except Exception:
                            pass
                    try:
                        lve.unlink()
                    except Exception:
                        pass

    def action_payslip_done(self):
        res = super().action_payslip_done()
        self._sync_reconciliation_settlements()
        return res

    def _get_worked_day_lines(self, *args, **kwargs):
        """
        Harmonizes Odoo's native Worked Days tab lines with our Reconciliation Engine:
        Ensures Extra Hours / Overtime line matches the net remaining extra hours after Step 1 lateness settlement.
        """
        res = super()._get_worked_day_lines(*args, **kwargs)
        for payslip in self:
            if payslip.employee_id and payslip.date_from and payslip.date_to:
                net_extra_hrs = round(payslip.attendance_gross_overtime - payslip.lateness_covered_by_extra_hours, 2)
                for line in res:
                    code = line.get('code') or ''
                    work_entry_type = self.env['hr.work.entry.type'].browse(line.get('work_entry_type_id')) if line.get('work_entry_type_id') else None
                    if code in ['OVERTIME', 'EXTRA', 'OUT'] or (work_entry_type and ('overtime' in work_entry_type.name.lower() or 'extra' in work_entry_type.name.lower())):
                        line['number_of_hours'] = max(0.0, net_extra_hrs)
                        line['number_of_days'] = round(max(0.0, net_extra_hrs) / 8.0, 2)
                        emp = payslip.employee_id
                        w = emp.wage if emp else 0.0
                        hourly_rate = w / 240.0
                        line['amount'] = round(max(0.0, net_extra_hrs) * hourly_rate, 3)
        return res

    def _convert_flexible_rest_days_to_ars(self):
        """
        Automatic Flexible Rest Day Conversion:
        Converts 'Absent' (ABS / ABSENT) work entries on unworked rest days to 'Rest Day' (ARS)
        up to the earned rest day quota (Method 2: 1 Rest Day earned per 6 Worked Days).
        Safely handles validated work entries without raising Invalid Operation errors.
        """
        rest_type = False
        if 'hr.work.entry' in self.env:
            rest_type = self.env['hr.work.entry.type'].sudo().search([
                '|', ('code', '=', 'ARS'), ('name', 'ilike', 'Rest')
            ], limit=1)

        for payslip in self:
            try:
                if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                    continue

                attendances = self.env['hr.attendance'].sudo().search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('check_in', '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                    ('check_in', '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max))
                ])
                worked_dates = set(att.check_in.date() for att in attendances)

                if rest_type and 'hr.work.entry' in self.env:
                    WorkEntry = self.env['hr.work.entry'].sudo()
                    we_fields = WorkEntry._fields

                    start_field = None
                    for candidate in ['date_start', 'date_from', 'start_datetime', 'date']:
                        if candidate in we_fields:
                            start_field = candidate
                            break

                    stop_field = None
                    for candidate in ['date_stop', 'date_to', 'end_datetime', 'date']:
                        if candidate in we_fields:
                            stop_field = candidate
                            break

                    if not start_field or not stop_field:
                        continue

                    domain = [
                        ('employee_id', '=', payslip.employee_id.id),
                        (start_field, '>=', datetime.datetime.combine(payslip.date_from, datetime.time.min)),
                        (stop_field, '<=', datetime.datetime.combine(payslip.date_to, datetime.time.max))
                    ]
                    work_entries = WorkEntry.search(domain).sorted(start_field)

                    for we in work_entries:
                        code = (we.work_entry_type_id.code or '').strip()
                        name = (we.work_entry_type_id.name or '').lower()
                        if not we.work_entry_type_id.is_leave and code not in ['LEAVE500', 'UNPAID', 'ABSENT', 'ABS'] and 'absent' not in name:
                            start_val = getattr(we, start_field, None)
                            if start_val:
                                we_date = start_val.date() if isinstance(start_val, (datetime.datetime, datetime.date)) else None
                                if we_date:
                                    worked_dates.add(we_date)

                    # Method 2: Earn 1 Rest Day for every 6 Worked Days
                    worked_days_count = len(worked_dates)
                    allowed_rest_days = worked_days_count // 6

                    converted_count = 0
                    for we in work_entries:
                        start_val = getattr(we, start_field, None)
                        if not start_val:
                            continue
                        we_date = start_val.date() if isinstance(start_val, (datetime.datetime, datetime.date)) else None
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

    def _sync_reconciliation_settlements(self):
        """
        1. Upload monthly overtime earned to Extra Hours Balance.
        2. Apply Step 1 extra hours deduction and Step 2 annual leave deduction.
        """
        for payslip in self:
            if not payslip.employee_id:
                continue

            # Upload monthly overtime earned & apply Step 1 lateness deduction to Extra Hours Balance
            net_extra_hours_change = payslip.attendance_gross_overtime - payslip.lateness_covered_by_extra_hours
            if 'hr.attendance.overtime.line' in self.env and net_extra_hours_change != 0.0:
                OvertimeLine = self.env['hr.attendance.overtime.line'].sudo()
                existing_line = OvertimeLine.search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('date', '=', payslip.date_to),
                    ('compensable_as_leave', '=', True),
                ], limit=1)

                vals = {
                    'employee_id': payslip.employee_id.id,
                    'date': payslip.date_to,
                    'duration': net_extra_hours_change,
                    'manual_duration': net_extra_hours_change,
                    'compensable_as_leave': True,
                    'status': 'approved',
                }
                if existing_line:
                    existing_line.write(vals)
                else:
                    OvertimeLine.create(vals)

            # Step 2: Annual Leave Deduction for Lateness
            if payslip.lateness_covered_by_annual_leave > 0:
                leave_types = self.env['hr.leave.type'].sudo().search([
                    '|', '|',
                    ('name', '=', 'Annual Leave'),
                    ('name', 'ilike', 'Annual'),
                    ('name', 'ilike', 'Paid')
                ])
                leave_type = leave_types[0] if leave_types else None
                if leave_type:
                    existing_leave = self.env['hr.leave'].sudo().search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('request_date_from', '<=', payslip.date_to),
                        ('request_date_to', '>=', payslip.date_from),
                        ('holiday_status_id', '=', leave_type.id),
                        ('name', 'ilike', 'Lateness Settlement')
                    ], limit=1)

                    hours_to_deduct = payslip.lateness_covered_by_annual_leave
                    days_to_deduct = round(hours_to_deduct / 8.0, 2)

                    if not existing_leave:
                        leave_vals = {
                            'name': 'Monthly Lateness Settlement via Annual Leave',
                            'employee_id': payslip.employee_id.id,
                            'holiday_status_id': leave_type.id,
                            'request_date_from': payslip.date_to,
                            'request_date_to': payslip.date_to,
                            'number_of_days': days_to_deduct,
                        }
                        if 'number_of_hours' in self.env['hr.leave']._fields:
                            leave_vals['number_of_hours'] = hours_to_deduct

                        new_leave = self.env['hr.leave'].sudo().create(leave_vals)
                        new_leave.sudo().write({'state': 'validate'})
                        if hasattr(new_leave, '_create_resource_calendar_leaves'):
                            try:
                                new_leave._create_resource_calendar_leaves()
                            except Exception:
                                pass
                    else:
                        update_vals = {'number_of_days': days_to_deduct, 'state': 'validate'}
                        if 'number_of_hours' in self.env['hr.leave']._fields:
                            update_vals['number_of_hours'] = hours_to_deduct
                        existing_leave.sudo().write(update_vals)

            # Recompute Extra Hours Balance display field if present
            if hasattr(payslip, '_compute_employee_extra_hours_balance'):
                payslip._compute_employee_extra_hours_balance()

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

    def _get_available_annual_leave_hours(self):
        """
        Gets available annual leave balance in hours for the employee:
        - Exact match for 'Annual Leave'.
        - Converts allocations stored in Days to Hours (1 Day = 8.0 Hours).
        """
        self.ensure_one()
        if not self.employee_id:
            return 0.0

        leave_types = self.env['hr.leave.type'].sudo().search([
            '|', '|', '|', '|',
            ('name', '=', 'Annual Leave'),
            ('name', 'ilike', 'Annual'),
            ('name', 'ilike', 'Paid'),
            ('name', 'ilike', 'سنوي'),
            ('name', 'ilike', 'إجازة')
        ])
        if not leave_types:
            leave_types = self.env['hr.leave.type'].sudo().search([])

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

        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id', 'in', leave_types.ids)
        ])

        for lve in leaves:
            if hasattr(lve, 'number_of_hours') and lve.number_of_hours:
                total_taken_hours += lve.number_of_hours
            elif hasattr(lve, 'number_of_days') and lve.number_of_days:
                total_taken_hours += (lve.number_of_days * 8.0)

        return max(0.0, total_allocated_hours - total_taken_hours)

    def _get_reconciled_attendance_variance(self):
        """
        Factory Flexible 6-Day Work Week & Monthly Rest Day Quota Reconciliation:
        - Ratio: 6 Working Days to 1 Rest Day.
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

        # 4. Monthly Rest Day Quota Reconciliation (Method 2 Ratio)
        if worked_days_count > target_work_days:
            # Employee worked extra days beyond monthly target -> Extra worked days count as Overtime!
            extra_worked_days = worked_days_count - target_work_days
            total_ot += (extra_worked_days * 8.0)
        else:
            unworked_days = total_days_in_month - worked_days_count
            if unworked_days > allowed_rest_days:
                # Employee took more off days than earned rest day quota -> Excess unworked days count as Undertime
                excess_unworked_days = unworked_days - allowed_rest_days
                total_undertime += (excess_unworked_days * 8.0)

        return {
            'total_ot': total_ot,
            'total_undertime': total_undertime,
            'net_variance': total_ot - total_undertime
        }
