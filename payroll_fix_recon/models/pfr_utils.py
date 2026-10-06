# -*- coding: utf-8 -*-
"""Shared constants and pure helpers (no ORM writes)."""
from datetime import date, datetime, time, timedelta

import pytz

DAILY_HOURS = 8.0
OT_MIN_HOURS = 0.75          # 45 min: minimum extra time to qualify as overtime
LATE_MIN_HOURS = 0.25        # 15 min: grace before undertime is registered
OT_RATE = 1.25
PH_RATE = 1.5
REST_DAY_OT_HOURS = DAILY_HOURS * PH_RATE      # unused earned rest day => 12h extra
HOURLY_DIVISOR = 240.0
ANNUAL_DAY_DIVISOR = 30.0
REST_CYCLE_DAYS = 6                            # 1 rest day per 6 physical days
MONTHLY_REST_ALLOWANCE = 4
DEFAULT_TZ = 'Asia/Amman'

OLD_MODULES = ('factory_attendance_payroll', 'reconciliation_payroll')

ATTENDANCE_CODES = {'WORK100', 'WORK1000', 'ATTENDANCE', 'ATTD'}
ABSENT_CODES = {'ABSENT', 'ABS'}
PUBLIC_HOLIDAY_CODES = {'PHD', 'GTO', 'HOLIDAY'}
TRAVEL_CODES = {'TRV', 'TRAVEL', 'TRAVEL_LEAVE'}
SICK_CODES = {'SIK', 'SICK', 'STO'}
UNPAID_CODES = {'UNPAID', 'LEAVE500', 'UNP', 'LEAVEUNPAID', 'UN_PAID', 'SICKLEAVE0'}
OUT_OF_CONTRACT_CODES = {'OUTCON', 'OUT', 'OUT_OF_CONTRACT'}
REST_CODES = {'ARS', 'REST', 'RST', 'RESTDAY', 'REST_DAY'}
LATENESS_CODE = 'LATENESS'


def net_hours(raw_hours, break_hours):
    """Net worked hours after the lunch-break policy (>=6h full, >4h half, else none).
    Returns (net, deducted_break)."""
    if raw_hours >= 6.0:
        deducted = break_hours
    elif raw_hours > 4.0:
        deducted = break_hours / 2.0
    else:
        deducted = 0.0
    return max(0.0, raw_hours - deducted), deducted


def get_tz(name):
    try:
        return pytz.timezone(name or DEFAULT_TZ)
    except Exception:
        return pytz.timezone(DEFAULT_TZ)


def local_date(dt_utc_naive, tz):
    """Local calendar date of a naive-UTC datetime."""
    return pytz.utc.localize(dt_utc_naive).astimezone(tz).date()


def local_hour(dt_utc_naive, tz):
    loc = pytz.utc.localize(dt_utc_naive).astimezone(tz)
    return loc.hour + loc.minute / 60.0


def daterange(d_from, d_to):
    d = d_from
    while d <= d_to:
        yield d
        d += timedelta(days=1)


def utc_bounds(d_from, d_to):
    """Naive datetimes (widened by one day) for querying UTC fields by local dates."""
    return (datetime.combine(d_from - timedelta(days=1), time.min),
            datetime.combine(d_to + timedelta(days=1), time.max))


def split_months(d_from, d_to):
    cur = d_from
    while cur <= d_to:
        last = (cur.replace(day=28) + timedelta(days=4))
        last = last - timedelta(days=last.day)
        end = min(d_to, last)
        yield cur, end
        cur = end + timedelta(days=1)


def type_codes(wet):
    """Upper-cased (code, display_code) of a work entry type."""
    return ((wet.code or '').strip().upper(),
            (getattr(wet, 'display_code', '') or '').strip().upper())


def type_matches(wet, codes, name_terms=()):
    code, disp = type_codes(wet)
    name = (wet.name or '').lower()
    return code in codes or disp in codes or any(t in name for t in name_terms)


def we_date(we):
    """Date of a work entry across Odoo versions."""
    d = getattr(we, 'date', False)
    if d:
        return d
    ds = getattr(we, 'date_start', False)
    return ds.date() if ds else False


def we_date_domain(model, d_from, d_to):
    if 'date' in model._fields:
        return [('date', '>=', d_from), ('date', '<=', d_to)]
    return [('date_start', '>=', datetime.combine(d_from, time.min)),
            ('date_start', '<=', datetime.combine(d_to, time.max))]


def version_dates(rec):
    start = getattr(rec, 'contract_date_start', False) or getattr(rec, 'date_start', False)
    end = getattr(rec, 'contract_date_end', False) or getattr(rec, 'date_end', False)
    return start or False, end or False


def day_utc_bounds(target_date, tz):
    """Naive-UTC [start, next_day_start) of a local calendar day."""
    start = tz.localize(datetime.combine(target_date, time.min))
    end = start + timedelta(days=1)
    return (start.astimezone(pytz.utc).replace(tzinfo=None),
            end.astimezone(pytz.utc).replace(tzinfo=None))
