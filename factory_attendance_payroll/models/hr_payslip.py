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

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        for payslip in self:
            if payslip.employee_id and payslip.date_from and payslip.date_to:
                res = payslip._get_reconciled_attendance_variance()
                payslip.attendance_gross_overtime = res.get('total_ot', 0.0)
                payslip.attendance_gross_undertime = res.get('total_undertime', 0.0)
                payslip.attendance_net_reconciled = res.get('net_variance', 0.0)
            else:
                payslip.attendance_gross_overtime = 0.0
                payslip.attendance_gross_undertime = 0.0
                payslip.attendance_net_reconciled = 0.0

    def compute_sheet(self):
        self._compute_attendance_reconciliation_fields()
        res = super().compute_sheet()
        self._sync_net_overtime_to_extra_hours_balance()
        return res

    def action_payslip_done(self):
        res = super().action_payslip_done()
        self._sync_net_overtime_to_extra_hours_balance()
        return res

    def _sync_net_overtime_to_extra_hours_balance(self):
        """
        Bank net overtime hours to hr.attendance.overtime.line so that
        anabtawi_payroll_overtime displays it in Extra Hours Balance (Other Info tab).
        """
        if 'hr.attendance.overtime.line' not in self.env:
            return

        OvertimeLine = self.env['hr.attendance.overtime.line'].sudo()
        for payslip in self:
            if payslip.employee_id:
                net_ot = max(0.0, payslip.attendance_net_reconciled)
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

                if net_ot > 0:
                    if existing_line:
                        existing_line.write(vals)
                    else:
                        OvertimeLine.create(vals)
                else:
                    if existing_line:
                        existing_line.write({'duration': 0.0, 'manual_duration': 0.0})

                # Recompute employee_extra_hours_balance on payslip if method exists
                if hasattr(payslip, '_compute_employee_extra_hours_balance'):
                    payslip._compute_employee_extra_hours_balance()

    def _get_reconciled_attendance_variance(self):
        """
        Factory 7-Day Rolling Operational Cycle with 45-min Overtime Threshold:
        - Evaluates daily worked hours with 1h break deduction (shifts >= 6h).
        - Overtime is ONLY counted if daily excess is >= 45 minutes (0.75 hours).
        - Any 6 worked days in a rolling 7-day cycle are standard workdays (8h target).
        - The 7th day in a cycle is a Rest Day: if worked >= 45 mins, all net hours count as Overtime.
        - Offsets total undertime against total overtime.
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

        total_ot = 0.0
        total_undertime = 0.0
        standard_target = 8.0
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

            work_day_count += 1

            # Every 7th day in rolling cycle is treated as Rest Day
            if work_day_count % 7 == 0:
                # Rest Day: If worked >= 45 mins, all net hours count as Overtime
                if net_hrs >= min_ot_threshold:
                    total_ot += net_hrs
            else:
                # Regular Work Day (8.0h target)
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
