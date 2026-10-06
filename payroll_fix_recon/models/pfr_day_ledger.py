# -*- coding: utf-8 -*-
"""Single source of truth for an employee's calendar days inside a payslip period.

Every calendar day of the period is assigned to EXACTLY ONE bucket, so the worked-day
lines can never double count a day and always add up to the calendar length:

    OUT      outside the contract window
    PHD      physically worked on a public holiday          (1.5x line)
    WORK     physical check-in (or an attendance work entry)
    TRAVEL   travel leave (continuous calendar days)
    SICK / UNPAID / ('TYPE', id)   leave work entries, by type
    PH       unworked public holiday                        (paid, merged in WORK100)
    ABSENT   ABSENT work entry
    REST     any remaining free day = earned rest day       (paid, merged in WORK100)

The absent engine is the only place that decides how many free days an employee earns,
so the ledger never re-derives the rest quota.
"""
from collections import defaultdict
from datetime import datetime, time

from odoo import api, models

from . import pfr_utils as U

PRIORITY_LEAVE_KINDS = ('SICK', 'UNPAID')


class PfrLedger:
    """Plain result object of PfrDayLedger.build()."""

    def __init__(self, d_from, d_to):
        self.d_from, self.d_to = d_from, d_to
        self.eff_from, self.eff_to = d_from, d_to
        self.days = {}                       # date -> bucket
        self.kind_types = {}                 # bucket -> work entry type (for the payslip lines)
        self.holiday_dates = set()
        self.leave_calendar_dates = set()    # calendar days of validated hr.leave (no settlement leaves)
        self.physical_dates = set()          # every check-in date (holidays included)
        self.attendances = []                # [(local date, hr.attendance)]
        self.regular_net_hours = 0.0         # net hours of check-ins on normal days
        self.holiday_net_hours = 0.0         # net hours of check-ins on public holidays
        self.absent_hours = 0.0
        self.entry_hours = defaultdict(float)  # bucket -> work entry hours

    def dates(self, bucket):
        return sorted(d for d, b in self.days.items() if b == bucket)

    def count(self, bucket):
        return sum(1 for b in self.days.values() if b == bucket)

    @property
    def active_days(self):
        return max(0, (self.eff_to - self.eff_from).days + 1) if self.eff_from <= self.eff_to else 0

    @property
    def base_attendance_days(self):
        """WORK100 line: physical days + earned rest days + unworked public holidays."""
        return float(self.count('WORK') + self.count('REST') + self.count('PH'))

    @property
    def total_days(self):
        return float(len(self.days))


class PfrDayLedger(models.AbstractModel):
    _name = 'pfr.day.ledger'
    _description = 'Payroll Fix Recon - Day Ledger'

    # ------------------------------------------------------------------
    # Public holidays
    # ------------------------------------------------------------------
    @api.model
    def public_holiday_dates(self, d_from, d_to):
        """{calendar_id | False: set(dates)} of global (resource-less) calendar leaves."""
        res = defaultdict(set)
        if not d_from or not d_to or 'resource.calendar.leaves' not in self.env:
            return res
        lo, hi = U.utc_bounds(d_from, d_to)
        leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False), ('date_from', '<=', hi), ('date_to', '>=', lo)])
        tz = U.get_tz(self.env.company.resource_calendar_id.tz or self.env.user.tz)
        for lve in leaves:
            if not lve.date_from or not lve.date_to:
                continue
            for d in U.daterange(U.local_date(lve.date_from, tz), U.local_date(lve.date_to, tz)):
                if d_from <= d <= d_to:
                    res[lve.calendar_id.id or False].add(d)
        return res

    @api.model
    def holidays_for(self, holiday_map, calendar):
        return holiday_map.get(False, set()) | (holiday_map.get(calendar.id, set()) if calendar else set())

    # ------------------------------------------------------------------
    # Work entry classification
    # ------------------------------------------------------------------
    @api.model
    def classify_type(self, wet):
        """Bucket key of a work entry type."""
        if U.type_matches(wet, U.ABSENT_CODES) or (wet.name or '').strip().lower() == 'absent':
            return 'ABSENT'
        if U.type_matches(wet, U.OUT_OF_CONTRACT_CODES, ('out of contract',)):
            return 'OUT'
        if U.type_matches(wet, U.PUBLIC_HOLIDAY_CODES, ('public holiday',)):
            return 'PH'
        if U.type_matches(wet, U.TRAVEL_CODES, ('travel', 'سفر', 'مهمة')):
            return 'TRAVEL'
        if U.type_matches(wet, U.UNPAID_CODES, ('unpaid', 'بدون')):
            return 'UNPAID'
        if U.type_matches(wet, U.SICK_CODES, ('sick', 'مرضي')):
            return 'SICK'
        if U.type_matches(wet, U.ATTENDANCE_CODES, ('attendance',)):
            return 'ATT'
        if U.type_matches(wet, U.REST_CODES, ('rest',)):
            return 'REST'
        if U.type_matches(wet, {'OVERTIME', 'EXTRA', 'EXTRA_HOURS', 'OT'}):
            return 'IGNORE'
        return ('TYPE', wet.id)

    @api.model
    def is_travel_leave(self, leave):
        st = leave.holiday_status_id
        if not st:
            return False
        name = (st.name or '').lower()
        if any(t in name for t in ('travel', 'سفر', 'مهمة')):
            return True
        wet = getattr(st, 'work_entry_type_id', False)
        return bool(wet and self.classify_type(wet) == 'TRAVEL')

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    @api.model
    def build(self, employee, d_from, d_to):
        employee.ensure_one()
        L = PfrLedger(d_from, d_to)
        tz = employee._pfr_tz()

        # contract window
        c_start, c_end = employee._pfr_contract_window(d_from, d_to)
        if c_start and c_start > d_from:
            L.eff_from = c_start
        if c_end and c_end < d_to:
            L.eff_to = c_end

        # public holidays (calendar leaves + public-holiday work entries)
        hol_map = self.public_holiday_dates(d_from, d_to)
        L.holiday_dates = set(self.holidays_for(hol_map, employee.resource_calendar_id))

        # physical attendance, grouped by local date
        lo, hi = U.utc_bounds(d_from, d_to)
        atts = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id), ('check_in', '>=', lo), ('check_in', '<=', hi)])
        net_by_date = defaultdict(float)
        for att in atts:
            d = U.local_date(att.check_in, tz)
            if d_from <= d <= d_to:
                L.physical_dates.add(d)
                L.attendances.append((d, att))
                net_by_date[d] += att.net_worked_hours
        for d, hrs in net_by_date.items():
            if d in L.holiday_dates:
                L.holiday_net_hours += hrs
            else:
                L.regular_net_hours += hrs

        # work entries -> per-kind date sets
        att_we, absent, ph_we = set(), {}, set()
        leave_we = defaultdict(dict)          # kind -> {date: hours}
        WE = self.env['hr.work.entry'].sudo()
        entries = WE.search([('employee_id', '=', employee.id), ('state', '!=', 'cancelled')]
                            + U.we_date_domain(WE, d_from, d_to))
        for we in entries:
            d, wet = U.we_date(we), we.work_entry_type_id
            if not d or not wet or not (d_from <= d <= d_to):
                continue
            kind = self.classify_type(wet)
            if kind not in ("ATT", "OUT", "REST", "IGNORE"):
                L.kind_types.setdefault(kind, wet)
            hrs = we.duration or 0.0
            if kind == 'ATT':
                att_we.add(d)
            elif kind == 'PH':
                ph_we.add(d)
            elif kind == 'ABSENT':
                absent[d] = absent.get(d, 0.0) + hrs
            elif kind in ('OUT', 'REST', 'IGNORE'):
                continue
            else:
                leave_we[kind][d] = leave_we[kind].get(d, 0.0) + hrs
        L.holiday_dates |= ph_we

        # validated leaves: calendar days (rest-day logic) + travel days (continuous)
        travel = set()
        if 'hr.leave' in self.env:
            leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', employee.id), ('state', 'in', ['validate', 'validate1']),
                ('date_from', '<=', datetime.combine(d_to, time.max)),
                ('date_to', '>=', datetime.combine(d_from, time.min)),
                '!', ('name', 'ilike', 'Lateness Settlement')])
            for lve in leaves:
                l_from = lve.request_date_from or U.local_date(lve.date_from, tz)
                l_to = lve.request_date_to or U.local_date(lve.date_to, tz)
                for d in U.daterange(max(l_from, d_from), min(l_to, d_to)):
                    L.leave_calendar_dates.add(d)
                    if self.is_travel_leave(lve):
                        if lve.holiday_status_id.work_entry_type_id:
                            L.kind_types.setdefault('TRAVEL', lve.holiday_status_id.work_entry_type_id)
                        travel.add(d)

        # assign each calendar day to exactly one bucket
        leave_kinds = [k for k in PRIORITY_LEAVE_KINDS if k in leave_we] + \
                      [k for k in leave_we if k not in PRIORITY_LEAVE_KINDS and k != 'TRAVEL']
        for d in U.daterange(d_from, d_to):
            is_hol = d in L.holiday_dates
            if d < L.eff_from or d > L.eff_to:
                bucket = 'OUT'
            elif d in L.physical_dates:
                bucket = 'PHD' if is_hol else 'WORK'
            elif d in att_we and not is_hol:
                bucket = 'WORK'
            elif d in travel or d in leave_we.get('TRAVEL', {}):
                bucket = 'TRAVEL'
            elif any(d in leave_we[k] for k in leave_kinds):
                bucket = next(k for k in leave_kinds if d in leave_we[k])
            elif is_hol:
                bucket = 'PH'
            elif d in absent:
                bucket = 'ABSENT'
            else:
                bucket = 'REST'
            L.days[d] = bucket
            if bucket in ('ABSENT',):
                L.absent_hours += absent[d]
            elif bucket not in ('OUT', 'PHD', 'WORK', 'PH', 'REST'):
                L.entry_hours[bucket] += leave_we.get(bucket, {}).get(d) or U.DAILY_HOURS
        return L
