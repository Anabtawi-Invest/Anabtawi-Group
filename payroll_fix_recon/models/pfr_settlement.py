# -*- coding: utf-8 -*-
"""Monthly overtime / lateness figures and the 3-step lateness settlement.

    gross lateness = daily punch undertime + ABSENT work entry hours
    step 1  deduct 1:1 from banked Extra Hours (previous balance + this month's overtime)
    step 2  deduct from Annual Leave (only if the employee opted in)
    step 3  whatever is left is deducted from cash (hours x wage / 240)

Pure computation: nothing is written here.
"""
from collections import defaultdict

from odoo import api, models

from . import pfr_utils as U

EXTRA_NAMES = ('Extra Hours', 'إضافي')
ANNUAL_NAMES = ('Annual Leave', 'سنوي')
PTO_NAMES = ('Paid Time Off', 'مدفوع')


def leave_hours(rec):
    """Hours of an allocation / leave record (days are worth 8h)."""
    for fname, mult in (('number_of_days', 8.0), ('number_of_days_display', 8.0),
                        ('number_of_hours', 1.0), ('number_of_hours_display', 1.0)):
        if fname in rec._fields and rec[fname]:
            return rec[fname] * mult
    return 0.0


def recon_alloc_name(slip):
    month = slip.date_to.strftime('%B %Y') if slip.date_to else ''
    return f"Extra Hours Reconciliation: {month} - {slip.employee_id.name}"


class PfrSettlement(models.AbstractModel):
    _name = 'pfr.settlement'
    _description = 'Payroll Fix Recon - Lateness Settlement'

    # ------------------------------------------------------------------
    # Leave types & balances
    # ------------------------------------------------------------------
    @api.model
    def leave_types(self, company=None):
        LT = self.env['hr.leave.type'].sudo()

        def by_name(names):
            dom = ['|'] * (len(names) - 1) + [('name', 'ilike', n) for n in names]
            return LT.search(dom)

        company = company or self.env.company
        annual = company.fap_annual_leave_type_id or by_name(ANNUAL_NAMES)
        return {'extra': by_name(EXTRA_NAMES), 'annual': annual, 'pto': by_name(PTO_NAMES)}

    @api.model
    def balance_hours(self, emp_ids, type_ids):
        """{(emp_id, type_id): allocated hours - validated leave hours}."""
        bal = defaultdict(float)
        if not type_ids or not emp_ids:
            return bal
        dom = [('employee_id', 'in', emp_ids), ('state', '=', 'validate'), ('holiday_status_id', 'in', type_ids)]
        for alloc in self.env['hr.leave.allocation'].sudo().search(dom):
            bal[(alloc.employee_id.id, alloc.holiday_status_id.id)] += leave_hours(alloc)
        for lve in self.env['hr.leave'].sudo().search(dom):
            bal[(lve.employee_id.id, lve.holiday_status_id.id)] -= leave_hours(lve)
        return bal

    @api.model
    def preload(self, slips):
        """Bulk data shared by every payslip of one compute run."""
        emp_ids = slips.employee_id.ids
        d_min, d_max = min(slips.mapped('date_from')), max(slips.mapped('date_to'))
        types = self.leave_types(slips[:1].company_id)
        type_ids = list((types['extra'] | types['annual']).ids)
        pre = {'types': types, 'balance': self.balance_hours(emp_ids, type_ids),
               'approved_ot': defaultdict(float), 'banked': defaultdict(float), 'recon_alloc': {}}
        if 'hr.attendance.overtime.line' in self.env:
            lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', 'in', emp_ids), ('compensable_as_leave', '=', True), ('status', '=', 'approved')])
            for line in lines:
                if line.date < d_min:
                    pre['banked'][line.employee_id.id] += line.duration
                elif line.date <= d_max:
                    dur = (line.manual_duration if 'manual_duration' in line._fields else 0.0) or line.duration
                    if dur > 0:
                        pre['approved_ot'][(line.employee_id.id, line.date)] = dur
        if types['extra']:
            for alloc in self.env['hr.leave.allocation'].sudo().search([
                    ('employee_id', 'in', emp_ids), ('state', '=', 'validate'),
                    ('holiday_status_id', 'in', types['extra'].ids),
                    ('name', 'ilike', 'Extra Hours Reconciliation')]):
                pre['recon_alloc'][(alloc.employee_id.id, alloc.name)] = leave_hours(alloc)
        return pre

    # ------------------------------------------------------------------
    # Overtime
    # ------------------------------------------------------------------
    @api.model
    def overtime_hours(self, slip, L, pre):
        """Approved overtime weighted by rate (1.25 regular, 1.5 public holiday, 12h per unused rest day)."""
        emp = slip.employee_id
        approved = pre['approved_ot']
        by_date = defaultdict(list)
        for d, att in L.attendances:
            by_date[d].append(att)

        total = 0.0
        for d, atts in by_date.items():
            line_ot = approved.get((emp.id, d), 0.0)
            if not (line_ot > 0 or any(a.overtime_status == 'approved' or a.validated_overtime_hours > 0
                                       for a in atts)):
                continue                                    # unapproved extra hours never reach the payslip
            if d in L.holiday_dates or any(a.is_public_holiday for a in atts):
                total += sum(a.net_worked_hours or a.worked_hours for a in atts) * U.PH_RATE
            elif line_ot > 0:
                total += line_ot * U.OT_RATE
            else:
                day_ot = sum(a.validated_overtime_hours or a.daily_overtime_hours for a in atts
                             if a.overtime_status == 'approved' or a.validated_overtime_hours > 0
                             or a.daily_overtime_hours >= U.OT_MIN_HOURS)
                if day_ot >= U.OT_MIN_HOURS:
                    total += day_ot * U.OT_RATE

        # worked more regular days than the monthly target (full periods only)
        active = L.active_days
        if not getattr(slip, 'termination_clearance', False) and active >= 25:
            regular_days = [d for d in L.physical_dates if d not in L.holiday_dates]
            extra_days = len(regular_days) - (active - active // 7)
            if extra_days > 0:
                approved_days = sum(1 for d in L.physical_dates if approved.get((emp.id, d), 0) > 0)
                total += min(extra_days, approved_days) * U.DAILY_HOURS * U.OT_RATE

        # earned rest days that were worked instead of taken
        total_days = (slip.date_to - slip.date_from).days + 1
        worked = len(L.physical_dates)
        if worked:
            off = sum(1 for d in U.daterange(slip.date_from, slip.date_to)
                      if d not in L.physical_dates and (d in L.leave_calendar_dates or d in L.holiday_dates))
            rest_taken = max(0, total_days - worked - off)
            total += max(0, U.MONTHLY_REST_ALLOWANCE - rest_taken) * U.REST_DAY_OT_HOURS
            return total, float(rest_taken)
        return total, 0.0

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------
    @api.model
    def compute(self, slip, L, pre):
        """Values for the payslip reconciliation fields."""
        emp = slip.employee_id
        company = slip.company_id or self.env.company
        exempt = emp.is_manager_exempt()

        gross_ot, rest_taken, punch = 0.0, 0.0, 0.0
        if not exempt:                                       # managers: no hourly lateness / overtime
            if getattr(company, 'enable_overtime_calculation', True):
                gross_ot, rest_taken = self.overtime_hours(slip, L, pre)
            punch = sum(a.daily_undertime_hours for d, a in L.attendances
                        if not a.is_public_holiday and d in L.days and L.days[d] != 'OUT')
        gross_ot = round(gross_ot, 2)
        gross_ut = round(punch + L.absent_hours, 2)          # absent days are settled like lateness

        # Extra Hours available before this payslip
        types = pre['types']
        extra_ids = types['extra'].ids
        bal = pre['balance']
        current_recon = max((slip.extra_hours_allocated_days or 0.0) * 8.0,
                            pre['recon_alloc'].get((emp.id, recon_alloc_name(slip)), 0.0))
        prior_alloc = max(0.0, sum(bal.get((emp.id, t), 0.0) for t in extra_ids) - current_recon)
        prev_extra = max(prior_alloc, round(pre['banked'].get(emp.id, 0.0), 2))
        total_avail = round(prev_extra + gross_ot, 2)

        covered_extra = round(min(gross_ut, total_avail), 2)                       # step 1
        remaining = round(gross_ut - covered_extra, 2)
        covered_annual = 0.0
        if remaining > 0.01 and emp.allow_annual_leave_lateness_deduction:        # step 2
            annual = max(0.0, sum(bal.get((emp.id, t), 0.0) for t in types['annual'].ids))
            covered_annual = round(min(remaining, annual), 2)
            remaining = round(remaining - covered_annual, 2)
        return {
            'attendance_gross_overtime': gross_ot,
            'rest_days_taken': rest_taken,
            'attendance_gross_undertime': gross_ut,
            'attendance_net_reconciled': round(gross_ot - gross_ut, 2),
            'total_extra_hours_available': total_avail,
            'lateness_covered_by_extra_hours': covered_extra,
            'remaining_extra_hours_balance': round(max(0.0, total_avail - covered_extra), 2),
            'lateness_covered_by_annual_leave': covered_annual,
            'undertime_cash_deduction_hours': remaining if remaining >= 0.01 else 0.0,   # step 3
        }
