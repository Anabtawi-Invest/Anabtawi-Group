# -*- coding: utf-8 -*-
"""Absent work entry automation + earned rest-day quota.

An unpunched day inside the contract is NOT absent when it is a public holiday, covered by
an approved leave / other work entry, or inside the employee's earned rest quota
(1 rest day per 6 physical days: Mondays for factory, Fridays for retail, calendar
off-days for head office). Every other unpunched working day gets one ABSENT entry.
"""
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import api, fields, models

from . import pfr_utils as U

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    @api.model
    def _cron_create_absent_work_entries(self):
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        self.search([('active', '=', True)])._pfr_create_absent_entries(yesterday.replace(day=1), yesterday)

    def generate_work_entries(self, date_start, date_stop, force=False):
        d_start, d_stop = fields.Date.to_date(date_start), fields.Date.to_date(date_stop)
        employees = self or self.search([('active', '=', True)])
        self._pfr_purge_invalid_entries(employees, d_start, d_stop)
        res = super().generate_work_entries(date_start, date_stop, force=force)
        if force:
            employees._pfr_create_absent_entries(d_start, d_stop)
        self._pfr_purge_invalid_entries(employees, d_start, d_stop)
        return res

    @api.model
    def _pfr_purge_invalid_entries(self, employees, d_from, d_to):
        """Work entries must have 0 < duration <= 24h."""
        if not employees or not d_from or not d_to:
            return
        WE = self.env['hr.work.entry'].sudo()
        bad = WE.search([('employee_id', 'in', employees.ids), ('state', '!=', 'validated'),
                         '|', ('duration', '<=', 0.0), ('duration', '>', 24.0)]
                        + U.we_date_domain(WE, d_from, d_to))
        bad.unlink()

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------
    def _pfr_create_absent_entries(self, date_from, date_to):
        date_from, date_to = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        if not self or not date_from or not date_to or date_from > date_to:
            return
        ledger = self.env['pfr.day.ledger']
        lo, hi = U.utc_bounds(date_from, date_to)
        holiday_map = ledger.public_holiday_dates(date_from, date_to)
        absent_type = self[:1]._pfr_get_absent_type()

        checkins = defaultdict(set)            # emp -> local dates with a check-in
        for att in self.env['hr.attendance'].sudo().search([
                ('employee_id', 'in', self.ids), ('check_in', '>=', lo), ('check_in', '<=', hi)]):
            d = U.local_date(att.check_in, att.employee_id._pfr_tz())
            if date_from <= d <= date_to:
                checkins[att.employee_id.id].add(d)

        leave_days = self._pfr_sync_leave_entries(date_from, date_to)   # emp -> dates

        WE = self.env['hr.work.entry'].sudo()
        covered = defaultdict(set)             # emp -> dates carrying a non-absent work entry
        for we in WE.search([('employee_id', 'in', self.ids), ('state', '!=', 'cancelled')]
                            + U.we_date_domain(WE, date_from, date_to)):
            wet = we.work_entry_type_id
            if wet and ledger.classify_type(wet) != 'ABSENT' and U.we_date(we):
                covered[we.employee_id.id].add(U.we_date(we))

        for m_from, m_to in U.split_months(date_from, date_to):
            for emp in self:
                emp._pfr_apply_month(m_from, m_to, absent_type, holiday_map, checkins[emp.id],
                                     leave_days[emp.id] | covered[emp.id])

    def _pfr_apply_month(self, m_from, m_to, absent_type, holiday_map, checkins, blocked):
        self.ensure_one()
        c_start, c_end = self._pfr_contract_window(m_from, m_to)
        holidays = self.env['pfr.day.ledger'].holidays_for(holiday_map, self.resource_calendar_id)
        eff_from = max(m_from, c_start) if c_start else m_from
        eff_to = min(m_to, c_end) if c_end else m_to

        # days outside the contract can never be absent
        for d in U.daterange(m_from, m_to):
            if d < eff_from or d > eff_to:
                self._pfr_remove_absence(d, absent_type)

        candidates = []
        for d in U.daterange(eff_from, eff_to):
            if d in holidays or d in checkins or d in blocked:
                self._pfr_remove_absence(d, absent_type)
            elif self._pfr_expected_hours(d) > 0:
                candidates.append(d)

        rest_days = self._pfr_pick_rest_days(candidates, len([d for d in checkins if m_from <= d <= m_to]),
                                             eff_from, eff_to)
        for d in candidates:
            if d in rest_days:
                self._pfr_remove_absence(d, absent_type)
            else:
                self._pfr_apply_absence(d, self._pfr_expected_hours(d), absent_type)

    def _pfr_pick_rest_days(self, candidates, month_checkins, eff_from, eff_to):
        """Candidate days that stay empty (earned rest days)."""
        station = self.employee_work_station or 'factory'
        if self._pfr_is_fixed_schedule():
            cal = self.resource_calendar_id
            if not cal:
                return set()
            working = {int(a.dayofweek) for a in cal.attendance_ids if a.dayofweek not in (False, None)}
            return {d for d in candidates if d.weekday() not in working}
        target = 0 if station == 'factory' else 4                    # Monday / Friday
        cap = sum(1 for d in U.daterange(eff_from, eff_to) if d.weekday() == target)
        earned = min(cap, month_checkins // U.REST_CYCLE_DAYS)
        picked = [d for d in candidates if d.weekday() == target][:earned]
        if len(picked) < earned:                                      # worked rest day -> any free day
            picked += [d for d in candidates if d not in picked][:earned - len(picked)]
        return set(picked)

    # ------------------------------------------------------------------
    # Leaves -> work entries
    # ------------------------------------------------------------------
    def _pfr_sync_leave_entries(self, date_from, date_to):
        """Make sure every validated leave day has a work entry. Returns {emp_id: set(dates)}."""
        days = defaultdict(set)
        if 'hr.leave' not in self.env:
            return days
        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', 'in', self.ids), ('state', 'in', ['validate', 'validate1']),
            ('date_from', '<=', datetime.combine(date_to, time.max)),
            ('date_to', '>=', datetime.combine(date_from, time.min)),
            '!', ('name', 'ilike', 'Lateness Settlement')])
        for lve in leaves:
            emp, tz = lve.employee_id, lve.employee_id._pfr_tz()
            l_from = lve.request_date_from or U.local_date(lve.date_from, tz)
            l_to = lve.request_date_to or U.local_date(lve.date_to, tz)
            wet = lve.holiday_status_id.work_entry_type_id
            for d in U.daterange(max(l_from, date_from), min(l_to, date_to)):
                days[emp.id].add(d)
                if wet:
                    emp._pfr_ensure_leave_entry(d, wet)
        return days

    def _pfr_day_entries(self, target_date, states=('cancelled',)):
        WE = self.env['hr.work.entry'].sudo()
        return WE.search([('employee_id', '=', self.id), ('state', 'not in', list(states))]
                         + U.we_date_domain(WE, target_date, target_date))

    def _pfr_ensure_leave_entry(self, target_date, wet):
        self.ensure_one()
        ledger = self.env['pfr.day.ledger']
        existing = self._pfr_day_entries(target_date)
        absent = existing.filtered(lambda w: w.work_entry_type_id and ledger.classify_type(w.work_entry_type_id) == 'ABSENT')
        if absent:
            absent.filtered(lambda w: w.state != 'validated').unlink()
        if existing - absent:
            return                                  # day already has a real entry: never duplicate
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return
        self._pfr_create_entry(target_date, U.DAILY_HOURS, wet, version, f"{self.name}: {wet.name}")

    # ------------------------------------------------------------------
    # Absent entry helpers
    # ------------------------------------------------------------------
    def _pfr_remove_absence(self, target_date, absent_type):
        self.ensure_one()
        ledger = self.env['pfr.day.ledger']
        stale = self._pfr_day_entries(target_date, states=('validated',)).filtered(
            lambda w: w.work_entry_type_id and (w.work_entry_type_id == absent_type
                                                or ledger.classify_type(w.work_entry_type_id) == 'ABSENT'))
        stale.unlink()

    def _pfr_apply_absence(self, target_date, duration, absent_type):
        self.ensure_one()
        dur = max(0.01, min(round(duration, 2), 24.0))
        existing = self._pfr_day_entries(target_date)
        if existing:
            if any(w.work_entry_type_id != absent_type and
                   self.env['pfr.day.ledger'].classify_type(w.work_entry_type_id) != 'ABSENT' for w in existing):
                return                              # a real entry exists on that day
            absents = existing.filtered(lambda w: w.state != 'validated')
            if absents:
                absents[:1].write(self._pfr_entry_vals(target_date, dur, absent_type))
                (absents[1:]).unlink()              # keep exactly one ABSENT entry per day
            return
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if version:
            self._pfr_create_entry(target_date, dur, absent_type, version, f"Absent: {self.name} - {target_date}")

    def _pfr_entry_vals(self, target_date, duration, wet):
        WE = self.env['hr.work.entry']
        vals = {'work_entry_type_id': wet.id, 'duration': duration}
        if 'date' in WE._fields:
            vals['date'] = target_date
        start = datetime.combine(target_date, time(8, 0))
        if 'date_start' in WE._fields:
            vals['date_start'] = start
        if 'date_stop' in WE._fields:
            vals['date_stop'] = start + timedelta(hours=duration)
        return vals

    def _pfr_create_entry(self, target_date, duration, wet, version, name):
        WE = self.env['hr.work.entry'].sudo()
        vals = dict(self._pfr_entry_vals(target_date, duration, wet), employee_id=self.id,
                    version_id=version.id, company_id=(self.company_id or self.env.company).id)
        if 'name' in WE._fields:
            vals['name'] = name
        return WE.create(vals)

    def _pfr_expected_hours(self, target_date):
        """Expected hours on a day: 0 outside any contract, planning hours for planning-based versions."""
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return 0.0
        if (getattr(version, 'work_entry_source', False) or '') == 'planning' and 'planning.slot' in self.env:
            start, end = self._pfr_day_utc_bounds(target_date)
            slots = self.env['planning.slot'].sudo().search([
                ('employee_id', '=', self.id), ('state', '=', 'published'),
                ('start_datetime', '<', end), ('end_datetime', '>', start)])
            return sum(slots.mapped('allocated_hours'))
        return U.DAILY_HOURS
