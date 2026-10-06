# -*- coding: utf-8 -*-
import calendar
import logging
from collections import defaultdict

from odoo import api, fields, models

from . import pfr_utils as U

_logger = logging.getLogger(__name__)

RECON_FIELDS = (
    'attendance_gross_overtime', 'rest_days_taken', 'attendance_gross_undertime',
    'attendance_net_reconciled', 'total_extra_hours_available', 'lateness_covered_by_extra_hours',
    'lateness_covered_by_annual_leave', 'remaining_extra_hours_balance', 'undertime_cash_deduction_hours',
)

# display order of the worked-day lines
LINE_SEQUENCE = {'WORK': 1, 'PHD': 5, 'TRAVEL': 10, 'SICK': 11, 'UNPAID': 15,
                 'ABSENT': 25, 'LATENESS': 26, 'OUT': 90}


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    attendance_gross_overtime = fields.Float(
        string="Monthly Overtime Earned", compute="_compute_attendance_reconciliation_fields", store=True)
    rest_days_taken = fields.Float(
        string="Rest Days Taken", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Unworked days excluding public holidays and approved leave. Allowance is 4; each unused "
             "rest day adds 8 x 1.5 hours to Monthly Overtime Earned.")
    attendance_gross_undertime = fields.Float(
        string="Monthly Lateness / Undertime", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Daily punch lateness plus ABSENT work entry hours.")
    attendance_net_reconciled = fields.Float(
        string="Net Reconciled Hours", compute="_compute_attendance_reconciliation_fields", store=True)
    total_extra_hours_available = fields.Float(
        string="Total Extra Hours Available", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Previous Extra Hours balance plus Monthly Overtime Earned.")
    remaining_extra_hours_balance = fields.Float(
        string="Remaining Extra Hours Balance", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Extra Hours left after step 1.")
    lateness_covered_by_extra_hours = fields.Float(
        string="Step 1: Lateness Deducted from Extra Hours",
        compute="_compute_attendance_reconciliation_fields", store=True)
    lateness_covered_by_annual_leave = fields.Float(
        string="Step 2: Lateness Deducted from Annual Leave",
        compute="_compute_attendance_reconciliation_fields", store=True)
    undertime_cash_deduction_hours = fields.Float(
        string="Step 3: Remaining Lateness Deducted from Cash",
        compute="_compute_attendance_reconciliation_fields", store=True)
    pfr_paid_days = fields.Float(
        string="Paid Days", compute="_compute_pfr_paid_days",
        help="Days paid by the Actual Salary rule: calendar days minus out-of-contract and unpaid leave.")
    pfr_days_in_month = fields.Integer(string="Days in Month", compute="_compute_pfr_days_in_month")
    is_reconciled = fields.Boolean(string="Attendance Reconciled", default=False, copy=False)
    extra_hours_allocated_days = fields.Float(
        string="Extra Hours Added to Allocation", default=0.0, copy=False)

    # ------------------------------------------------------------------
    # Reconciliation figures (in-memory only)
    # ------------------------------------------------------------------
    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        ready = getattr(self.env.registry, 'ready', True)
        if not ready or self.env.context.get('install_mode') or self.env.context.get('module_installation'):
            for slip in self:
                slip.update(dict.fromkeys(RECON_FIELDS, 0.0))
            return
        valid = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to
                              and (s.state in ('draft', 'verify') or not s.id))
        for slip in self - valid:                       # confirmed / cancelled slips keep their figures
            slip.update({f: slip[f] for f in RECON_FIELDS})
        if not valid:
            return
        settlement, ledger = self.env['pfr.settlement'], self.env['pfr.day.ledger']
        pre = settlement.preload(valid)
        for slip in valid:
            L = ledger.build(slip.employee_id, slip.date_from, slip.date_to)
            slip.update(settlement.compute(slip, L, pre))

    # ------------------------------------------------------------------
    # Worked days (one line per bucket, built from the day ledger)
    # ------------------------------------------------------------------
    def _pfr_wage(self):
        self.ensure_one()
        version = self.version_id if 'version_id' in self._fields else False
        return (version.wage if version else 0.0) or self.employee_id.wage or 0.0

    def _pfr_line_type(self, L, kind):
        """Work entry type used for a worked-day line."""
        WET = self.env['hr.work.entry.type'].sudo()
        known = L.kind_types.get('PH' if kind == 'PHD' else kind)
        if known:
            return known
        search = {
            'WORK': (U.ATTENDANCE_CODES, 'attendance'), 'PHD': (U.PUBLIC_HOLIDAY_CODES, 'public holiday'),
            'TRAVEL': (U.TRAVEL_CODES, 'travel'), 'SICK': (U.SICK_CODES, 'sick'),
            'UNPAID': (U.UNPAID_CODES, 'unpaid'), 'ABSENT': (U.ABSENT_CODES, 'absent'),
            'LATENESS': ({U.LATENESS_CODE, 'LAT', 'LATE'}, 'lateness'),
            'OUT': (U.OUT_OF_CONTRACT_CODES, 'out of contract'),
        }.get(kind)
        found = WET.browse()
        if search:
            codes, term = search
            found = WET.search(['|', '|', ('code', 'in', list(codes)), ('display_code', 'in', list(codes)),
                                ('name', 'ilike', term)], limit=1)
        if not found and kind == 'PHD':
            return self._pfr_line_type(L, 'WORK')
        if not found and kind == 'ABSENT':
            return self.employee_id._pfr_get_absent_type()
        if not found and kind in ('LATENESS', 'OUT'):
            found = WET.create({'name': 'Lateness / Undertime Deduction' if kind == 'LATENESS' else 'Out of Contract',
                                'code': U.LATENESS_CODE if kind == 'LATENESS' else 'OUTCON',
                                'display_code': 'LAT' if kind == 'LATENESS' else 'OUT',
                                'is_leave': False, 'round_days': 'NO', 'round_days_type': 'DOWN'})
        return found[:1]

    def _get_worked_day_lines(self, *args, **kwargs):
        if len(self) != 1:
            return super()._get_worked_day_lines(*args, **kwargs)
        slip = self
        if not (slip.employee_id and slip.date_from and slip.date_to):
            return super()._get_worked_day_lines(*args, **kwargs)
        L = self.env['pfr.day.ledger'].build(slip.employee_id, slip.date_from, slip.date_to)
        days_in_month = calendar.monthrange(slip.date_to.year, slip.date_to.month)[1]
        day_rate = slip._pfr_wage() / float(days_in_month)

        # (kind, days, hours)
        rows = []
        we_only = len([d for d in L.dates('WORK') if d not in L.physical_dates])
        rows.append(('WORK', L.base_attendance_days,
                     L.regular_net_hours + U.DAILY_HOURS * (L.count('REST') + L.count('PH') + we_only)))
        rows.append(('PHD', float(L.count('PHD')), L.holiday_net_hours * U.PH_RATE))
        for bucket in sorted({b for b in L.days.values() if b not in ('OUT', 'PHD', 'WORK', 'PH', 'REST', 'ABSENT')},
                             key=lambda b: (LINE_SEQUENCE.get(b, 12), str(b))):
            rows.append((bucket, float(L.count(bucket)), L.entry_hours.get(bucket, 0.0)))
        rows.append(('ABSENT', float(L.count('ABSENT')), L.absent_hours))
        rows.append(('OUT', float(L.count('OUT')), L.count('OUT') * U.DAILY_HOURS))

        lines = []
        for kind, days, hours in rows:
            if days <= 0.0:
                continue
            wet = slip._pfr_line_type(L, kind)
            if not wet:
                continue
            seq_key = kind if isinstance(kind, str) else None
            lines.append({
                'name': wet.name,
                'sequence': LINE_SEQUENCE.get(seq_key, 12),
                'work_entry_type_id': wet.id,
                'number_of_days': days,
                'number_of_hours': round(hours, 2),
                'amount': 0.0 if kind == 'OUT' else round(days * wet._pfr_pay_factor() * day_rate, 3),
            })
        cash_hrs = slip.undertime_cash_deduction_hours
        if cash_hrs >= 0.01:                                  # informational: step 3 leftover
            wet = slip._pfr_line_type(L, 'LATENESS')
            lines.append({
                'name': 'Lateness / Undertime Deduction', 'sequence': LINE_SEQUENCE['LATENESS'],
                'work_entry_type_id': wet.id, 'number_of_days': 0.0, 'number_of_hours': round(cash_hrs, 2),
                'amount': round(cash_hrs * slip._pfr_wage() / U.HOURLY_DIVISOR, 3),
            })
        return lines

    @api.depends('date_to')
    def _compute_pfr_days_in_month(self):
        for slip in self:
            slip.pfr_days_in_month = calendar.monthrange(slip.date_to.year, slip.date_to.month)[1] \
                if slip.date_to else 30

    @api.depends('worked_days_line_ids.number_of_days', 'worked_days_line_ids.work_entry_type_id',
                 'worked_days_line_ids.work_entry_type_id.pfr_pay_percent')
    def _compute_pfr_paid_days(self):
        for slip in self:
            slip.pfr_paid_days = slip._pfr_sum_paid_days()

    def _pfr_sum_paid_days(self):
        """Every line except out-of-contract and unpaid leave. ABSENT days stay paid here because
        their cost is carried exactly once by the lateness settlement (steps 1-3)."""
        self.ensure_one()
        total = 0.0
        for wd in self.worked_days_line_ids:
            wet = wd.work_entry_type_id
            if U.type_matches(wet, U.OUT_OF_CONTRACT_CODES, ('out of contract',)) \
                    or U.type_matches(wet, U.UNPAID_CODES, ('unpaid', 'بدون')) \
                    or U.type_matches(wet, {U.LATENESS_CODE, 'LAT', 'LATE'}):
                continue
            total += (wd.number_of_days or 0.0) * wet._pfr_pay_factor()
        return total

    # ------------------------------------------------------------------
    # Compute sheet
    # ------------------------------------------------------------------
    def compute_sheet(self):
        slips = self.filtered(lambda s: s.employee_id and s.date_from and s.date_to
                              and s.state in ('draft', 'verify'))
        by_period = defaultdict(lambda: self.env['hr.employee'])    # one batched engine run per period
        for slip in slips:                              # explicit writes belong here, not in computes
            by_period[(slip.date_from, slip.date_to)] |= slip.employee_id
        for (d_from, d_to), employees in by_period.items():
            employees._pfr_create_absent_entries(d_from, d_to)
        if slips:
            self.env.flush_all()
            slips._compute_attendance_reconciliation_fields()
            slips._pfr_apply_termination_inputs()
            for slip in slips:
                slip.worked_days_line_ids = [(5, 0, 0)] + [(0, 0, v) for v in slip._get_worked_day_lines()]
        res = super().compute_sheet()
        slips.with_context(skip_reconcile_revert=True).write({'is_reconciled': True})
        slips._pfr_reset_preview()
        return res

    def _pfr_reset_preview(self):
        """The side preview shows a stored PDF; drop it on draft slips so it is rebuilt from the new lines."""
        for fname in ('payslip_file', 'payslip_pdf', 'payslip_report_file'):
            if fname in self._fields and self._fields[fname].type == 'binary':
                drafts = self.filtered(lambda s: s.state in ('draft', 'verify'))
                if drafts:
                    drafts.with_context(skip_reconcile_revert=True).sudo().write({fname: False})

    @api.onchange('employee_id', 'struct_id')
    def _onchange_termination_clearance(self):
        self._compute_attendance_reconciliation_fields()
        self._pfr_apply_termination_inputs()

    def _compute_issues(self):
        """hr_payroll stores `issues` as JSON; some payloads contain records as dict keys
        (e.g. base.automation) and make json.dumps raise. Never let that block a slip write."""
        for slip in self:
            try:
                super(HrPayslip, slip)._compute_issues()
            except (TypeError, ValueError) as exc:
                _logger.warning("[payroll_fix_recon] slip %s: issues not serialisable (%s), cleared", slip.id, exc)
                slip.issues = False

    def _action_create_account_move(self):
        by_company = defaultdict(lambda: self.env['hr.payslip'])
        for slip in self:
            by_company[slip.company_id] |= slip
        res = True
        for slips in by_company.values():
            res = super(HrPayslip, slips)._action_create_account_move()
        return res
