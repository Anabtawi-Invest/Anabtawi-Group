# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

import pytz

from odoo import http
from odoo.http import request


class PortalCheckInController(http.Controller):

    @staticmethod
    def _format_hours(hours_value):
        hours_value = max(hours_value or 0.0, 0.0)
        hours = int(hours_value)
        minutes = int(round((hours_value - hours) * 60))
        if minutes == 60:
            hours += 1
            minutes = 0
        return "%s hrs %s min" % (hours, minutes)

    @staticmethod
    def _format_datetime_to_user_time(dt_value):
        if not dt_value:
            return False
        user_tz = pytz.timezone(request.env.user.tz or 'UTC')
        dt_utc = pytz.utc.localize(dt_value) if dt_value.tzinfo is None else dt_value.astimezone(pytz.utc)
        return dt_utc.astimezone(user_tz).strftime('%H:%M')

    def _get_current_employee(self):
        """Return the logged-in user's employee record, if any."""
        return request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.user.id)],
            limit=1,
        )

    def _get_today_bounds_utc(self):
        """Return today's [start, end) bounds in UTC based on user timezone."""
        user_tz = pytz.timezone(request.env.user.tz or 'UTC')
        now_local = datetime.now(user_tz)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)
        return start_utc, end_utc

    @http.route(['/my/check-in'], type='http', auth='user', website=True)
    def portal_my_check_in(self, **kwargs):
        employee = self._get_current_employee()
        recent_attendances = request.env['hr.attendance']
        today_check_in = False
        today_check_out = False
        if employee:
            start_utc, end_utc = self._get_today_bounds_utc()
            recent_attendances = request.env['hr.attendance'].sudo().search(
                [
                    ('employee_id', '=', employee.id),
                    ('check_in', '>=', start_utc),
                    ('check_in', '<', end_utc),
                ],
                order='check_in desc',
            )
            if recent_attendances:
                today_check_in = recent_attendances[-1].check_in
                checkout_candidates = recent_attendances.filtered(lambda a: a.check_out)
                today_check_out = checkout_candidates[0].check_out if checkout_candidates else False
        values = {
            'page_name': 'my_check_in',
            'employee': employee,
            'state': employee.attendance_state if employee else False,
            'hours_today_display': self._format_hours(employee.hours_today) if employee else "0 hrs 0 min",
            'recent_attendances': recent_attendances,
            'today_check_in': self._format_datetime_to_user_time(today_check_in),
            'today_check_out': self._format_datetime_to_user_time(today_check_out),
            'show_success': kwargs.get('success') == '1',
            'show_no_employee': kwargs.get('error') == 'no_employee',
        }
        return request.render('portal_check_in.portal_my_check_in', values)

    @http.route(
        ['/my/check-in/toggle'],
        type='http',
        auth='user',
        website=True,
        methods=['POST'],
        csrf=True,
    )
    def portal_toggle_check_in(self, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/check-in?error=no_employee')

        geo_information = {
            'latitude': kwargs.get('latitude'),
            'longitude': kwargs.get('longitude'),
        }
        # Attendance is always toggled for the current user's own employee only.
        employee._attendance_action_change(geo_information=geo_information)
        return request.redirect('/my/check-in?success=1')
