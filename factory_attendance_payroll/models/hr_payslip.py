import datetime
from collections import defaultdict
from odoo import models, fields, api

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    attendance_gross_overtime = fields.Float(
        string="Gross Overtime Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Total overtime hours accumulated from attendance before reconciliation."
    )
    attendance_gross_undertime = fields.Float(
        string="Gross Late / Undertime Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Total late/undertime hours accumulated from attendance before reconciliation."
    )
    attendance_net_reconciled = fields.Float(
        string="Net Reconciled Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Net reconciled hours (Overtime minus Undertime) used for payslip allowance/deduction."
    )

    # 3-Tier Waterfall Settlement Breakdown Fields
    undertime_covered_by_extra_hours = fields.Float(
        string="Undertime Settled via Extra Hours",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Tier 1: Undertime deficit hours offset using banked Extra Hours Balance."
    )
    undertime_covered_by_annual_leave = fields.Float(
        string="Undertime Settled via Annual Leave",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Tier 2: Undertime deficit hours offset using available Annual Leave balance."
    )
    undertime_cash_deduction_hours = fields.Float(
        string="Undertime Remaining for Cash Deduction",
        compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Tier 3: Final remaining undertime deficit hours deducted from monthly cash salary."
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        for payslip in self:
            if payslip.employee_id and payslip.date_from and payslip.date_to:
                res = payslip._get_reconciled_attendance_variance()
                gross_ot = res.get('total_ot', 0.0)
                gross_ut = res.get('total_undertime', 0.0)
                net_var = res.get('net_variance', 0.0)

                payslip.attendance_gross_overtime = gross_ot
                payslip.attendance_gross_undertime = gross_ut
                payslip.attendance_net_reconciled = net_var

                # 3-Tier Cascade Waterfall Settlement for Net Undertime Deficit (< 0)
                if net_var < 0.0:
                    deficit = abs(net_var)

                    # Tier 1: Check available Extra Hours Balance
                    extra_hours_avail = payslip._get_available_extra_hours_balance()
                    covered_extra = min(deficit, extra_hours_avail)
                    rem_deficit = deficit - covered_extra

                    # Tier 2: Check available Annual Leave balance
                    covered_leave = 0.0
                    if rem_deficit > 0.0:
                        annual_leave_avail = payslip._get_available_annual_leave_hours()
                        covered_leave = min(rem_deficit, annual_leave_avail)
                        rem_deficit = rem_deficit - covered_leave

                    # Tier 3: Remaining deficit goes to Monthly Cash Salary Deduction
                    payslip.undertime_covered_by_extra_hours = covered_extra
                    payslip.undertime_covered_by_annual_leave = covered_leave
                    payslip.undertime_cash_deduction_hours = rem_deficit
                else:
                    payslip.undertime_covered_by_extra_hours = 0.0
                    payslip.undertime_covered_by_annual_leave = 0.0
                    payslip.undertime_cash_deduction_hours = 0.0
            else:
                payslip.attendance_gross_overtime = 0.0
                payslip.attendance_gross_undertime = 0.0
                payslip.attendance_net_reconciled = 0.0
                payslip.undertime_covered_by_extra_hours = 0.0
                payslip.undertime_covered_by_annual_leave = 0.0
                payslip.undertime_cash_deduction_hours = 0.0

    def compute_sheet(self):
        self._compute_attendance_reconciliation_fields()
        res = super().compute_sheet()
        self._sync_reconciliation_settlements()
        return res

    def action_payslip_done(self):
        res = super().action_payslip_done()
        self._sync_reconciliation_settlements()
        return res

    def _sync_reconciliation_settlements(self):
        """
        1. Bank net overtime (if > 0) to Extra Hours Balance.
        2. Deduct Tier 1 extra hours and Tier 2 annual leaves when payslip is processed.
        """
        for payslip in self:
            if not payslip.employee_id:
                continue

            # Case A: Net Overtime (> 0) -> Bank to Extra Hours Balance
            if payslip.attendance_net_reconciled > 0:
                if 'hr.attendance.overtime.line' in self.env:
                    OvertimeLine = self.env['hr.attendance.overtime.line'].sudo()
                    net_ot = payslip.attendance_net_reconciled
                    existing_line = OvertimeLine.search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('date', '=', payslip.date_to),
                        ('compensable_as_leave', '=', True),
                    ], limit=1)

                    vals = {
                        'employee_id': payslip.employee_id.id,
                        'date': payslip.date_to,
                        'duration': net_ot,
                        'manual_duration': net_ot,
                        'compensable_as_leave': True,
                        'status': 'approved',
                    }
                    if existing_line:
                        existing_line.write(vals)
                    else:
                        OvertimeLine.create(vals)

            # Case B: Tier 1 Extra Hours Consumption for Undertime Deficit
            elif payslip.undertime_covered_by_extra_hours > 0:
                if 'hr.attendance.overtime.line' in self.env:
                    OvertimeLine = self.env['hr.attendance.overtime.line'].sudo()
                    ded_hours = -abs(payslip.undertime_covered_by_extra_hours)
                    existing_ded_line = OvertimeLine.search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('date', '=', payslip.date_to),
                        ('duration', '<', 0),
                    ], limit=1)

                    vals = {
                        'employee_id': payslip.employee_id.id,
                        'date': payslip.date_to,
                        'duration': ded_hours,
                        'manual_duration': ded_hours,
                        'compensable_as_leave': True,
                        'status': 'approved',
                    }
                    if existing_ded_line:
                        existing_ded_line.write(vals)
                    else:
                        OvertimeLine.create(vals)

            # Case C: Tier 2 Annual Leave Consumption for Undertime Deficit
            if payslip.undertime_covered_by_annual_leave > 0 and payslip.state == 'done':
                leave_type = self.env['hr.leave.type'].sudo().search([
                    ('name', 'ilike', 'Annual')
                ], limit=1)
                if leave_type:
                    existing_leave = self.env['hr.leave'].sudo().search([
                        ('employee_id', '=', payslip.employee_id.id),
                        ('request_date_from', '=', payslip.date_to),
                        ('holiday_status_id', '=', leave_type.id),
                    ], limit=1)
                    if not existing_leave:
                        self.env['hr.leave'].sudo().create({
                            'name': 'Undertime Reconciliation Annual Leave Settlement',
                            'employee_id': payslip.employee_id.id,
                            'holiday_status_id': leave_type.id,
                            'request_date_from': payslip.date_to,
                            'request_date_to': payslip.date_to,
                            'number_of_hours': payslip.undertime_covered_by_annual_leave,
                            'state': 'validate',
                        })

            # Recompute Extra Hours Balance display field if present
            if hasattr(payslip, '_compute_employee_extra_hours_balance'):
                payslip._compute_employee_extra_hours_balance()

    def _get_available_extra_hours_balance(self):
        self.ensure_one()
        if not self.employee_id:
            return 0.0
        if hasattr(self, '_get_employee_extra_hours_balance'):
            return max(0.0, self._get_employee_extra_hours_balance())
        elif 'hr.attendance.overtime.line' in self.env:
            lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('compensable_as_leave', '=', True),
                ('status', '=', 'approved'),
            ])
            return max(0.0, sum(lines.mapped('duration')))
        return 0.0

    def _get_available_annual_leave_hours(self):
        self.ensure_one()
        if not self.employee_id:
            return 0.0
        allocations = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.name', 'ilike', 'Annual'),
        ])
        total_allocated = sum(allocations.mapped('number_of_hours_display')) if allocations else 0.0

        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.name', 'ilike', 'Annual'),
        ])
        total_taken = sum(leaves.mapped('number_of_hours')) if leaves else 0.0

        return max(0.0, total_allocated - total_taken)

    def _get_reconciled_attendance_variance(self):
        """
        Factory 7-Day Rolling Operational Cycle with Planning Shifts & 45-min Overtime Threshold:
        - Evaluates daily worked hours with 1h break deduction (shifts >= 6h).
        - Planning Slots / Working Schedule integration: target hours are evaluated against planned shift.
        - Overtime is ONLY counted if daily excess is >= 45 minutes (0.75 hours).
        - Any 6 worked days in a rolling 7-day cycle are standard workdays.
        - The 7th day in a cycle is a Rest Day: if worked >= 45 mins, all net hours count as Overtime.
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

        # 3. Planning Slots integration
        planning_slots_by_date = {}
        if 'planning.slot' in self.env:
            slots = self.env['planning.slot'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('start_datetime', '>=', datetime.datetime.combine(self.date_from, datetime.time.min)),
                ('end_datetime', '<=', datetime.datetime.combine(self.date_to, datetime.time.max))
            ])
            for slot in slots:
                s_date = slot.start_datetime.date()
                s_hrs = (slot.end_datetime - slot.start_datetime).total_seconds() / 3600.0
                planning_slots_by_date[s_date] = max(0.0, s_hrs - 1.0) if s_hrs >= 6.0 else s_hrs

        total_ot = 0.0
        total_undertime = 0.0
        min_ot_threshold = 0.75  # 45 minutes

        # Sort dates chronologically
        sorted_dates = sorted(daily_hours.keys())
        work_day_count = 0

        for att_date in sorted_dates:
            raw_hrs = daily_hours[att_date]

            # Apply 1h break deduction rule
            if raw_hrs >= 6.0:
                net_hrs = max(0.0, raw_hrs - 1.0)
            elif raw_hrs > 4.0:
                net_hrs = raw_hrs - 0.5
            else:
                net_hrs = raw_hrs

            # Determine planned shift target for this date
            if att_date in planning_slots_by_date:
                standard_target = planning_slots_by_date[att_date]
            else:
                standard_target = 8.0

            work_day_count += 1

            # Every 7th day in rolling cycle is treated as Rest Day
            if work_day_count % 7 == 0:
                # Rest Day: If worked >= 45 mins, all net hours count as Overtime
                if net_hrs >= min_ot_threshold:
                    total_ot += net_hrs
            else:
                # Regular Work Day
                if net_hrs > standard_target:
                    ot_excess = net_hrs - standard_target
                    # Overtime considered ONLY if daily excess is >= 45 mins (0.75h)
                    if ot_excess >= min_ot_threshold:
                        total_ot += ot_excess
                elif net_hrs < standard_target:
                    total_undertime += (standard_target - net_hrs)

        # Direct Reconciliation: Net Overtime minus Undertime
        net_variance = total_ot - total_undertime

        return {
            'total_ot': total_ot,
            'total_undertime': total_undertime,
            'net_variance': net_variance
        }
