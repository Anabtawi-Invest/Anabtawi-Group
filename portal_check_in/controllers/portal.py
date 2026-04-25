# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import logging
from urllib.parse import quote, unquote

import pytz

from odoo import http, _, fields
from odoo.exceptions import UserError
from odoo.http import request
from requests.exceptions import RequestException

_logger = logging.getLogger(__name__)


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
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.user.id)],
            limit=1,
        )
        _logger.info(
            "portal_check_in: resolved employee for user_id=%s -> employee_id=%s",
            request.env.user.id,
            employee.id if employee else False,
        )
        return employee

    def _get_available_overtime_authorization(self, employee):
        approval_model = request.env["approval.request"].sudo()
        if not employee or not hasattr(approval_model, "_get_available_preauthorized_request"):
            return request.env["approval.request"]
        return approval_model._get_available_preauthorized_request(
            employee, target_date=fields.Date.context_today(employee)
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

    @staticmethod
    def _safe_float(value):
        try:
            return float(value) if value not in (False, None, '') else False
        except (TypeError, ValueError):
            _logger.warning("portal_check_in: invalid float value received: %r", value)
            return False

    def _build_geo_information(self, employee, latitude=False, longitude=False):
        geo_information = {
            'mode': 'systray',
        }
        tracking_enabled = bool(employee.company_id.attendance_device_tracking)
        _logger.info(
            "portal_check_in: employee_id=%s company_id=%s company=%s tracking_enabled=%s",
            employee.id,
            employee.company_id.id,
            employee.company_id.name,
            tracking_enabled,
        )
        if not tracking_enabled:
            # Keep the mode explicit (systray) like native Odoo flow, but skip device/location data.
            return geo_information

        geo_information.update({
            'latitude': latitude,
            'longitude': longitude,
            'ip_address': request.geoip.ip,
            'browser': request.httprequest.user_agent.browser,
        })
        try:
            location = request.env['base.geocoder']._get_localisation(latitude, longitude)
        except (UserError, RequestException):
            location = _("Unknown")
        geo_information['location'] = location
        _logger.info(
            "portal_check_in: geo payload built for employee_id=%s -> lat=%s, lon=%s, ip=%s, browser=%s, location=%s",
            employee.id,
            latitude,
            longitude,
            geo_information.get('ip_address'),
            geo_information.get('browser'),
            location,
        )
        return geo_information

    @http.route(['/my/check-in'], type='http', auth='user', website=True)
    def portal_my_check_in(self, **kwargs):
        _logger.info(
            "portal_check_in: page opened by user_id=%s with kwargs=%s",
            request.env.user.id,
            kwargs,
        )
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
        required_weekly_hours = (
            employee._get_required_weekly_hours()
            if employee and hasattr(employee, "_get_required_weekly_hours")
            else 0.0
        )
        weekly_worked_hours = (
            employee.weekly_worked_hours
            if employee and "weekly_worked_hours" in employee._fields
            else 0.0
        )
        weekly_gate_reached = (
            employee._is_weekly_hours_threshold_reached()
            if employee and hasattr(employee, "_is_weekly_hours_threshold_reached")
            else False
        )
        available_overtime_authorization = (
            self._get_available_overtime_authorization(employee) if employee else request.env["approval.request"]
        )
        values = {
            'page_name': 'my_check_in',
            'employee': employee,
            'state': employee.attendance_state if employee else False,
            'device_tracking_enabled': employee.company_id.attendance_device_tracking if employee else False,
            'hours_today_display': self._format_hours(employee.hours_today) if employee else "0 hrs 0 min",
            'recent_attendances': recent_attendances,
            'today_check_in': self._format_datetime_to_user_time(today_check_in),
            'today_check_out': self._format_datetime_to_user_time(today_check_out),
            'show_success': kwargs.get('success') == '1',
            'show_no_employee': kwargs.get('error') == 'no_employee',
            'show_location_restricted': kwargs.get('error') == 'location_restricted',
            'location_restricted_message': unquote(kwargs.get('message', '')) if kwargs.get('message') else False,
            'weekly_worked_hours': weekly_worked_hours,
            'required_weekly_hours': required_weekly_hours,
            'weekly_gate_reached': weekly_gate_reached,
            'available_overtime_authorization': available_overtime_authorization,
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
        _logger.info(
            "portal_check_in: toggle requested by user_id=%s with raw kwargs keys=%s",
            request.env.user.id,
            sorted(kwargs.keys()),
        )
        employee = self._get_current_employee()
        if not employee:
            _logger.warning(
                "portal_check_in: no employee linked to user_id=%s",
                request.env.user.id,
            )
            return request.redirect('/my/check-in?error=no_employee')

        try:
            # Attendance is always toggled for the current user's own employee only.
            latitude = self._safe_float(kwargs.get('latitude'))
            longitude = self._safe_float(kwargs.get('longitude'))
            _logger.info(
                "portal_check_in: parsed geo values for employee_id=%s -> latitude=%s longitude=%s",
                employee.id,
                latitude,
                longitude,
            )
            geo_information = self._build_geo_information(employee, latitude=latitude, longitude=longitude)
            attendance = employee._attendance_action_change(geo_information)
            _logger.info(
                "portal_check_in: attendance toggled successfully for employee_id=%s attendance_id=%s new_state=%s",
                employee.id,
                attendance.id if attendance else False,
                employee.attendance_state,
            )
            return request.redirect('/my/check-in?success=1')
        except UserError as error:
            error_message = (error.args and error.args[0]) or _("لا يمكنك تسجيل الحضور من هذا الموقع.")
            _logger.warning(
                "portal_check_in: business validation blocked toggle for user_id=%s employee_id=%s reason=%s",
                request.env.user.id,
                employee.id,
                error_message,
            )
            message = quote(error_message)
            return request.redirect('/my/check-in?error=location_restricted&message=%s' % message)
        except Exception:
            _logger.exception(
                "portal_check_in: toggle failed for user_id=%s employee_id=%s",
                request.env.user.id,
                employee.id,
            )
            return request.redirect('/my/check-in?error=attendance_failed')
# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import logging
from urllib.parse import quote, unquote

import pytz

from odoo import http, _, fields
from odoo.exceptions import UserError
from odoo.http import request
from requests.exceptions import RequestException

_logger = logging.getLogger(__name__)


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
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.user.id)],
            limit=1,
        )
        _logger.info(
            "portal_check_in: resolved employee for user_id=%s -> employee_id=%s",
            request.env.user.id,
            employee.id if employee else False,
        )
        return employee

    def _get_available_overtime_authorization(self, employee):
        approval_model = request.env["approval.request"].sudo()
        if not employee or not hasattr(approval_model, "_get_available_preauthorized_request"):
            return request.env["approval.request"]
        return approval_model._get_available_preauthorized_request(
            employee, target_date=fields.Date.context_today(employee)
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

    @staticmethod
    def _safe_float(value):
        try:
            return float(value) if value not in (False, None, '') else False
        except (TypeError, ValueError):
            _logger.warning("portal_check_in: invalid float value received: %r", value)
            return False

    def _build_geo_information(self, employee, latitude=False, longitude=False):
        geo_information = {
            'mode': 'systray',
        }
        tracking_enabled = bool(employee.company_id.attendance_device_tracking)
        _logger.info(
            "portal_check_in: employee_id=%s company_id=%s company=%s tracking_enabled=%s",
            employee.id,
            employee.company_id.id,
            employee.company_id.name,
            tracking_enabled,
        )
        if not tracking_enabled:
            # Keep the mode explicit (systray) like native Odoo flow, but skip device/location data.
            return geo_information

        geo_information.update({
            'latitude': latitude,
            'longitude': longitude,
            'ip_address': request.geoip.ip,
            'browser': request.httprequest.user_agent.browser,
        })
        try:
            location = request.env['base.geocoder']._get_localisation(latitude, longitude)
        except (UserError, RequestException):
            location = _("Unknown")
        geo_information['location'] = location
        _logger.info(
            "portal_check_in: geo payload built for employee_id=%s -> lat=%s, lon=%s, ip=%s, browser=%s, location=%s",
            employee.id,
            latitude,
            longitude,
            geo_information.get('ip_address'),
            geo_information.get('browser'),
            location,
        )
        return geo_information

    @http.route(['/my/check-in'], type='http', auth='user', website=True)
    def portal_my_check_in(self, **kwargs):
        _logger.info(
            "portal_check_in: page opened by user_id=%s with kwargs=%s",
            request.env.user.id,
            kwargs,
        )
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
        required_weekly_hours = (
            employee._get_required_weekly_hours()
            if employee and hasattr(employee, "_get_required_weekly_hours")
            else 0.0
        )
        weekly_worked_hours = (
            employee.weekly_worked_hours
            if employee and "weekly_worked_hours" in employee._fields
            else 0.0
        )
        weekly_gate_reached = (
            employee._is_weekly_hours_threshold_reached()
            if employee and hasattr(employee, "_is_weekly_hours_threshold_reached")
            else False
        )
        available_overtime_authorization = (
            self._get_available_overtime_authorization(employee) if employee else request.env["approval.request"]
        )
        values = {
            'page_name': 'my_check_in',
            'employee': employee,
            'state': employee.attendance_state if employee else False,
            'device_tracking_enabled': employee.company_id.attendance_device_tracking if employee else False,
            'hours_today_display': self._format_hours(employee.hours_today) if employee else "0 hrs 0 min",
            'recent_attendances': recent_attendances,
            'today_check_in': self._format_datetime_to_user_time(today_check_in),
            'today_check_out': self._format_datetime_to_user_time(today_check_out),
            'show_success': kwargs.get('success') == '1',
            'show_no_employee': kwargs.get('error') == 'no_employee',
            'show_location_restricted': kwargs.get('error') == 'location_restricted',
            'location_restricted_message': unquote(kwargs.get('message', '')) if kwargs.get('message') else False,
            'weekly_worked_hours': weekly_worked_hours,
            'required_weekly_hours': required_weekly_hours,
            'weekly_gate_reached': weekly_gate_reached,
            'available_overtime_authorization': available_overtime_authorization,
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
        _logger.info(
            "portal_check_in: toggle requested by user_id=%s with raw kwargs keys=%s",
            request.env.user.id,
            sorted(kwargs.keys()),
        )
        employee = self._get_current_employee()
        if not employee:
            _logger.warning(
                "portal_check_in: no employee linked to user_id=%s",
                request.env.user.id,
            )
            return request.redirect('/my/check-in?error=no_employee')

        try:
            # Attendance is always toggled for the current user's own employee only.
            latitude = self._safe_float(kwargs.get('latitude'))
            longitude = self._safe_float(kwargs.get('longitude'))
            _logger.info(
                "portal_check_in: parsed geo values for employee_id=%s -> latitude=%s longitude=%s",
                employee.id,
                latitude,
                longitude,
            )
            geo_information = self._build_geo_information(employee, latitude=latitude, longitude=longitude)
            attendance = employee._attendance_action_change(geo_information)
            _logger.info(
                "portal_check_in: attendance toggled successfully for employee_id=%s attendance_id=%s new_state=%s",
                employee.id,
                attendance.id if attendance else False,
                employee.attendance_state,
            )
            return request.redirect('/my/check-in?success=1')
        except UserError as error:
            error_message = (error.args and error.args[0]) or _("لا يمكنك تسجيل الحضور من هذا الموقع.")
            _logger.warning(
                "portal_check_in: business validation blocked toggle for user_id=%s employee_id=%s reason=%s",
                request.env.user.id,
                employee.id,
                error_message,
            )
            message = quote(error_message)
            return request.redirect('/my/check-in?error=location_restricted&message=%s' % message)
        except Exception:
            _logger.exception(
                "portal_check_in: toggle failed for user_id=%s employee_id=%s",
                request.env.user.id,
                employee.id,
            )
            return request.redirect('/my/check-in?error=attendance_failed')
