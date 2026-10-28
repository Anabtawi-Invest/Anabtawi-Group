# -*- coding: utf-8 -*-
import calendar
import logging
from collections import defaultdict

from odoo import api, fields, models

from . import pfr_utils as U

_logger = logging.getLogger(__name__)

RECON_FIELDS = (
    'attendance_gross_overtime', 'overtime_holiday_hours', 'overtime_regular_hours', 'overtime_rest_hours',
    'rest_days_taken', 'attendance_gross_undertime',
    'attendance_net_reconciled', 'total_extra_hours_available', 'lateness_covered_by_extra_hours',
    'remaining_extra_hours_balance', 'total_pto_available', 'lateness_covered_by_pto',
    'remaining_pto_balance', 'lateness_covered_by_annual_leave', 'undertime_cash_deduction_hours',
)

# display order of the worked-day lines
LINE_SEQUENCE = {'WORK': 1, 'PHD': 5, 'TRAVEL': 10, 'SICK': 11, 'UNPAID': 15,
                 'ABSENT': 25, 'LATENESS': 26, 'OUT': 90}


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    attendance_gross_overtime = fields.Float(
        string="Monthly Overtime Earned", compute="_compute_attendance_reconciliation_fields", store=True)
    overtime_holiday_hours = fields.Float(
        string="Public Holiday Overtime (x1.5)", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Approved hours worked on public holidays, weighted x1.5. Part of Monthly Overtime Earned.")
    overtime_regular_hours = fields.Float(
        string="Regular Overtime (x1.25)", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Approved daily extra hours and extra worked days, weighted x1.25. Part of Monthly Overtime Earned.")
    overtime_rest_hours = fields.Float(
        string="Unused Rest Days Overtime", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Unused rest days of the monthly allowance, 8h x 1.5 each. Part of Monthly Overtime Earned.")
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
        help="Previous Extra Hours balance plus regular overtime (x1.25).")
    remaining_extra_hours_balance = fields.Float(
        string="Remaining Extra Hours Balance", compute="_compute_attendance_reconciliation_fields", store=True,
        help="Real hours left after step 1 (leftover earned OT divided by 1.25). Allocated on confirm.")
    lateness_covered_by_extra_hours = fields.Float(
        string="Step 1: Lateness Deducted from Extra Hours",
        compute="_compute_attendance_reconciliation_fields", store=True)
    total_pto_available = fields.Float(
        string="Total Paid Time Off Available", compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Previous PTO balance plus public-holiday overtime (x1.5) and unused rest days (12h each).")
    lateness_covered_by_pto = fields.Float(
        string="Step 2: Lateness Deducted from Paid Time Off",
        compute="_compute_attendance_reconciliation_fields", store=True)
    remaining_pto_balance = fields.Float(
        string="Remaining Paid Time Off Available", compute="_compute_attendance_reconciliation_fields",
        store=True,
        help="Real hours left after step 2 (leftover PH/rest divided by 1.5; prior PTO 1:1). "
             "Allocated on confirm.")
    lateness_covered_by_annual_leave = fields.Float(
        string="Step 3: Lateness Deducted from Annual Leave",
        compute="_compute_attendance_reconciliation_fields", store=True)
    undertime_cash_deduction_hours = fields.Float(
        string="Step 4: Remaining Lateness Deducted from Cash",
        compute="_compute_attendance_reconciliation_fields", store=True)
    pfr_paid_days = fields.Float(
        string="Paid Days", compute="_compute_pfr_paid_days",
        help="Days paid by the Actual Salary rule: calendar days minus out-of-contract and unpaid leave.")
    pfr_days_in_month = fields.Integer(string="Days in Month", compute="_compute_pfr_days_in_month")
    is_reconciled = fields.Boolean(string="Attendance Reconciled", default=False, copy=False)
    extra_hours_allocated_days = fields.Float(
        string="Extra Hours Added to Allocation", default=0.0, copy=False)
    pto_allocated_days = fields.Float(
        string="Paid Time Off Added to Allocation", default=0.0, copy=False)

    # ------------------------------------------------------------------
    # Reconciliation figures (in-memory only)
    # ------------------------------------------------------------------
    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_reconciliation_fields(self):
        ready = getattr(self.env.registry, 'ready', True)
        if not ready or self.env.context.get('install_mode') or self.env.context.get('module_installation'):
            for slip in self:                           # module load / upgrade: keep every stored figure as it is
                slip.update({f: slip[f] for f in RECON_FIELDS})
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
        # never attach a line to a type of another company: the multi-company record rule would make the
        # salary rules fail with an access error when they read the worked days
        company = self.company_id
        has_company = 'company_id' in WET._fields
        mine = lambda t: (not has_company) or (not t.company_id) or t.company_id == company
        company_domain = [('company_id', 'in', [False, company.id])] if has_company else []
        known = L.kind_types.get('PH' if kind == 'PHD' else kind)
        if known and mine(known):
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
            found = WET.search(company_domain + ['|', '|', ('code', 'in', list(codes)),
                                                 ('display_code', 'in', list(codes)),
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

        # Layout: days close at the calendar days of the period, hours close at days x 8.
        # The table is derived from the CASH deduction (what is really taken from the salary), so that
        #     Absent hours + Lateness hours == Attendance Deduction hours.
        # Everything that Extra Hours / PTO / Annual Leave already settled is paid time and sits in Attendance.
        absent_days = float(L.count('ABSENT'))
        cash_hours = max(0.0, slip.undertime_cash_deduction_hours or 0.0)
        # whole 8h days of the cash remain Absent days; the rest (< 8h) stays as lateness hours
        absent_shown = min(absent_days, float(int(cash_hours / U.DAILY_HOURS + 1e-9)))
        punch_lateness = max(0.0, cash_hours - absent_shown * U.DAILY_HOURS)
        reconciled_days = absent_days - absent_shown   # absent days settled by Extra Hours / PTO / Annual

        # (kind, days, hours)
        rows = []
        # public holidays (worked or not) are paid on their own line, never inside Attendance
        attendance_days = float(L.count('WORK') + L.count('REST')) + reconciled_days
        rows.append(('WORK', attendance_days, max(0.0, attendance_days * U.DAILY_HOURS - punch_lateness)))
        phd_days = float(L.count('PHD') + L.count('PH'))
        rows.append(('PHD', phd_days, phd_days * U.DAILY_HOURS))
        for bucket in sorted({b for b in L.days.values() if b not in ('OUT', 'PHD', 'WORK', 'PH', 'REST', 'ABSENT')},
                             key=lambda b: (LINE_SEQUENCE.get(b, 12), str(b))):
            bucket_days = float(L.count(bucket))
            rows.append((bucket, bucket_days, bucket_days * U.DAILY_HOURS))
        rows.append(('ABSENT', absent_shown, absent_shown * U.DAILY_HOURS))
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
        if punch_lateness >= 0.01:                            # cash hours that do not make a whole absent day
            wet = slip._pfr_line_type(L, 'LATENESS')
            lines.append({
                'name': 'Lateness / Undertime Deduction', 'sequence': LINE_SEQUENCE['LATENESS'],
                'work_entry_type_id': wet.id, 'number_of_days': 0.0, 'number_of_hours': round(punch_lateness, 2),
                'amount': round(punch_lateness * slip._pfr_wage() / U.HOURLY_DIVISOR, 3),
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
            slips.mapped('struct_id')._pfr_ensure_rules()   # picks up newly added rules without a reinstall
            for slip in slips:
                slip.worked_days_line_ids = [(5, 0, 0)] + [(0, 0, v) for v in slip._get_worked_day_lines()]
        res = super().compute_sheet()
        slips.with_context(skip_reconcile_revert=True).write({'is_reconciled': True})
        slips._pfr_apply_worked_day_amounts()                        # daily-wage calendar amounts
        slips._pfr_reset_preview()
        return res

    def _pfr_line_calendar_amount(self, wd):
        """Amount of one worked-day line by the daily-wage calendar rule (None if the wage is unknown)."""
        self.ensure_one()
        if not self.date_to or self.state not in ('draft', 'verify'):
            return None
        wage = self._pfr_wage()
        if wage <= 0:
            return None
        daily = wage / float(calendar.monthrange(self.date_to.year, self.date_to.month)[1])
        wet = wd.work_entry_type_id
        kind = self.env['pfr.day.ledger'].classify_type(wet) if wet else 'PAID'
        code = (wet.code or '').upper() if wet else ''
        days = wd.number_of_days or 0.0
        if kind in ('OUT', 'IGNORE'):
            return 0.0
        if kind in ('ABSENT', 'UNPAID'):            # shown for information: days x daily wage
            return round(days * daily, 3)
        if code in ('LATENESS', 'LAT', 'LATE'):
            return round((wd.number_of_hours or 0.0) * daily / 8.0, 3)
        return round(days * (wet._pfr_pay_factor() if wet else 1.0) * daily, 3)

    def _pfr_apply_worked_day_amounts(self):
        """Write the calendar amounts on the worked-day lines (end of Compute Sheet)."""
        for slip in self:
            for wd in slip.worked_days_line_ids:
                amount = slip._pfr_line_calendar_amount(wd)
                if amount is not None and abs((wd.amount or 0.0) - amount) > 0.0005:
                    wd.sudo().write({'amount': amount})

    def _pfr_reset_preview(self):
        """The side preview (o_attachment_preview) shows the PDF attachment saved on the payslip.
        On draft slips drop the stale PDF and, for a handful of slips, render a fresh one so the
        preview matches the new lines. Bulk runs only drop it (rendering is one wkhtmltopdf per slip)."""
        drafts = self.filtered(lambda s: s.id and s.state in ('draft', 'verify'))
        if not drafts:
            return
        Attachment = self.env['ir.attachment'].sudo()
        stale = Attachment.search([('res_model', '=', 'hr.payslip'), ('res_id', 'in', drafts.ids),
                                   ('mimetype', '=', 'application/pdf'), ('res_field', '=', False)])
        stale.unlink()
        if len(drafts) > 5:
            return
        for slip in drafts:
            try:
                report = slip.struct_id.report_id if 'report_id' in slip.struct_id._fields else False
                report = report or self.env.ref('hr_payroll.action_report_payslip', raise_if_not_found=False)
                if not report:
                    continue
                pdf, _fmt = report.sudo()._render_qweb_pdf(report.report_name, slip.ids)
                Attachment.create({
                    'name': f"{slip.name or 'Payslip'}.pdf", 'raw': pdf, 'mimetype': 'application/pdf',
                    'res_model': 'hr.payslip', 'res_id': slip.id,
                })
            except Exception:
                _logger.exception("[payroll_fix_recon] could not refresh the PDF preview for slip %s", slip.id)

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
