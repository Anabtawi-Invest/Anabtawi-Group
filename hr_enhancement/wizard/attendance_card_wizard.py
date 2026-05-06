# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytz
from babel.dates import format_date as babel_format_date

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Datetime as DatetimeFN
from odoo.tools.float_utils import float_round
from odoo.tools.image import image_data_uri

try:
    from babel.core import Locale, UnknownLocaleError
except ImportError:  # pragma: no cover
    Locale = None
    UnknownLocaleError = Exception


class HrEnhancementAttendanceCardWizard(models.TransientModel):
    _name = 'hr.enhancement.attendance.card.wizard'
    _description = 'Attendance Cards Report Wizard'

    employee_id = fields.Many2one(
        'hr.employee',
        required=True,
        string='Employee',
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from and wiz.date_to and wiz.date_from > wiz.date_to:
                raise UserError(_("The period end date must not be before the start date."))

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('hr_enhancement.action_report_attendance_card').report_action(self)

    @staticmethod
    def _float_hours_to_time_str(hours):
        if not hours:
            return '00:00:00'
        total_seconds = int(float_round(float(hours) * 3600, precision_digits=0))
        hs, remainder = divmod(max(total_seconds, 0), 3600)
        mins, secs = divmod(remainder, 60)
        return '%d:%02d:%02d' % (hs, mins, secs)

    def _weekday_name(self, d: date):
        self.ensure_one()
        lc = (
            (self.employee_id.user_id.partner_id.lang if self.employee_id.user_id else False)
            or self.env.user.lang
            or 'en_US'
        )
        lc_babel = lc.replace('-', '_')
        if Locale is None:
            return d.strftime('%A')
        try:
            loc = Locale.parse(lc_babel)
        except (UnknownLocaleError, ValueError, AttributeError):
            loc = Locale('en_US')
        return babel_format_date(d, 'EEEE', locale=loc)

    def _calendar_is_work_day(self, employee, ref_date):
        cal = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        if not cal:
            return True
        if getattr(cal, 'flexible_hours', False):
            return True
        return cal._works_on_date(ref_date)

    def _leave_hours_for_day(self, employee, ref_day):
        Leave = self.env['hr.leave'].sudo()
        tz_name = employee._get_tz() or employee.tz or self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz_name)
        utc = pytz.utc
        start_local = user_tz.localize(datetime.combine(ref_day, time.min))
        end_local = user_tz.localize(datetime.combine(ref_day, time.max))
        start_utc = start_local.astimezone(utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(utc).replace(tzinfo=None)
        leaves = Leave.search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', end_utc),
            ('date_to', '>=', start_utc),
        ])
        overlap_seconds = 0
        for leave in leaves:
            lf = leave.date_from
            lt = leave.date_to
            if not lf or not lt:
                continue
            if lt <= start_utc or lf >= end_utc:
                continue
            seg_from = max(lf, start_utc)
            seg_to = min(lt, end_utc)
            overlap_seconds += int((seg_to - seg_from).total_seconds())
        return overlap_seconds / 3600

    def _get_report_lines(self):
        self.ensure_one()
        emp = self.employee_id

        attendance_by_date = defaultdict(lambda: self.env['hr.attendance'])
        records = (
            self.env['hr.attendance'].search([
                ('employee_id', '=', emp.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ], order='check_in asc')
        )
        for att in records:
            attendance_by_date[att.date] |= att

        lines = []
        cur = self.date_from
        while cur <= self.date_to:
            atts = attendance_by_date.get(cur)
            is_work_day = self._calendar_is_work_day(emp, cur)
            leave_h = self._leave_hours_for_day(emp, cur)

            weekday = self._weekday_name(cur)

            if not atts:
                vacation_text = ''
                if not is_work_day:
                    vacation_text = _('Day off')
                lines.append({
                    'weekday': weekday,
                    'weekday_note': '',
                    'date_in': '',
                    'time_in': '',
                    'date_out': '',
                    'time_out': '',
                    'vacation': vacation_text,
                    'leave': self._float_hours_to_time_str(leave_h),
                    'attendance': '00:00:00',
                })
                cur += timedelta(days=1)
                continue

            first_att = atts[0]
            last_att = atts[-1]
            cin_dt = DatetimeFN.context_timestamp(emp, first_att.check_in)
            checkout = last_att.check_out
            cout_dt = DatetimeFN.context_timestamp(emp, checkout) if checkout else None

            worked = sum(atts.mapped('worked_hours'))

            lines.append({
                'weekday': weekday,
                'weekday_note': '',
                'date_in': cin_dt.strftime('%d/%m/%Y'),
                'time_in': cin_dt.strftime('%H:%M:%S'),
                'date_out': cout_dt.strftime('%d/%m/%Y') if cout_dt else '',
                'time_out': cout_dt.strftime('%H:%M:%S') if cout_dt else '',
                'vacation': '',
                'leave': self._float_hours_to_time_str(leave_h),
                'attendance': self._float_hours_to_time_str(worked),
            })
            cur += timedelta(days=1)

        return lines

    def _pdf_header_note(self):
        """Optional second line under the title (e.g. contract labels). Empty by default."""
        self.ensure_one()
        return ''


class ReportHrEnhancementAttendanceCard(models.AbstractModel):
    _name = 'report.hr_enhancement.report_attendance_card'
    _description = 'Attendance Card PDF Report'

    @api.model
    def _standard_anabtawi_banner_values(self):
        """Shared footer (and helpers) for all qweb-pdf reports using ae_pdf_* templates."""
        user = self.env.user
        emp = user.employee_id
        raw_id = ''
        if emp:
            raw_id = (emp.identification_id or emp.barcode or '').strip()
        if not raw_id:
            raw_id = str(user.id)
        if raw_id.isdigit():
            disp_id = raw_id.zfill(6)
        else:
            disp_id = raw_id
        now_utc = fields.Datetime.now()
        now_local = fields.Datetime.context_timestamp(user, now_utc)
        return {
            'ae_print_id': disp_id,
            'ae_print_name': (user.name or '').upper(),
            'ae_print_date': now_local.strftime('%d/%m/%Y'),
            'ae_print_time': now_local.strftime('%H:%M:%S'),
            'ae_licensed_line': _('Licensed To: Anabtawi Sweets'),
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['hr.enhancement.attendance.card.wizard'].browse(docids)
        wiz = wizard[:1]
        if not wiz:
            return {}
        company = wiz.employee_id.company_id or self.env.company
        lines = wiz._get_report_lines()
        period_from_fmt = wiz.date_from.strftime('%d/%m/%Y')
        period_to_fmt = wiz.date_to.strftime('%d/%m/%Y')
        subtitle = _('From %(df)s To %(dt)s') % {'df': period_from_fmt, 'dt': period_to_fmt}
        banner = dict(self._standard_anabtawi_banner_values())
        merged = dict(data or {})
        ret = {
            **merged,
            'doc_ids': docids,
            'doc_model': 'hr.enhancement.attendance.card.wizard',
            'docs': wizard,
            'company': company,
            'employee': wiz.employee_id,
            'period_from': wiz.date_from,
            'period_to': wiz.date_to,
            'period_from_fmt': period_from_fmt,
            'period_to_fmt': period_to_fmt,
            'report_lines': lines,
            'rowspan': len(lines) or 1,
            'image_data_uri': image_data_uri,
            'title': _('Attendance Cards'),
            'lbl_from': _('From'),
            'lbl_to': _('To'),
            'h_emp_no': _('Emp No.'),
            'h_emp_name': _('Emp Name'),
            'h_week_day': _('Week Day'),
            'h_date_in': _('Date In'),
            'h_time_in': _('Time In'),
            'h_date_out': _('Date Out'),
            'h_time_out': _('Time Out'),
            'h_vacation': _('Vacation'),
            'h_leave': _('Leave'),
            'h_attendance': _('Attendance'),
            'ae_report_title': _('Attendance Cards'),
            'ae_report_subtitle': subtitle,
            'ae_report_header_note': wiz._pdf_header_note(),
        }
        ret.update(banner)
        return ret
