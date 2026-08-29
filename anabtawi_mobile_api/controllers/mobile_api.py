import logging
import os
from datetime import datetime, time

import pytz

from odoo import _, fields, http
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)


def _json(data, status=200):
    return request.make_json_response(data, status=status)


def _error(code, message, status=400):
    return _json({"error": code, "message": message}, status=status)



def _client_ip():
    forwarded = request.httprequest.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.httprequest.environ.get("REMOTE_ADDR", "") or ""

def _parse_bearer(value):
    parts = (value or "").strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _payload():
    try:
        if request.httprequest.is_json:
            return request.get_json_data() or {}
    except Exception:
        pass
    return dict(request.params or {})


def _as_float(value):
    try:
        if value in (None, False, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class AnabtawiMobileAPI(http.Controller):
    def _client_ip(self):
        headers = request.httprequest.headers
        forwarded_for = headers.get("X-Forwarded-For") or ""
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        return request.httprequest.environ.get("REMOTE_ADDR", "")

    def _safe_has_group(self, user, group_xmlid):
        try:
            return bool(user.sudo().with_context(lang="en_US").has_group(group_xmlid))
        except Exception:
            return False

    def _eligible_mobile_user(self, user):
        """Allow Employee App login for any active Odoo user linked to an active employee.

        This check applies only to Employee App API login. It does not override or
        restrict normal Odoo backend (/odoo, /web/login) access from multiple devices.
        """
        if not user or not user.active:
            return False
        employee = request.env["hr.employee"].sudo().search([
            ("user_id", "=", user.id),
            ("active", "=", True),
        ], limit=1)
        return bool(employee)

    @http.route(
        "/anabtawi/mobile/auth/login",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def mobile_login(self, **kwargs):
        try:
            payload = request.get_json_data() if request.httprequest.is_json else {}
        except Exception:
            payload = {}
        if not payload:
            payload = {
                "login": request.params.get("login"),
                "password": request.params.get("password"),
                "device_uid": request.params.get("device_uid"),
                "device_name": request.params.get("device_name"),
                "platform": request.params.get("platform"),
                "manufacturer": request.params.get("manufacturer"),
                "model_name": request.params.get("model_name"),
                "app_version": request.params.get("app_version"),
                "ip_address": request.params.get("ip_address"),
            }
        if not payload and kwargs:
            payload = {k: v for k, v in kwargs.items() if v is not False}

        login_name = (payload.get("login") or "").strip()
        password = payload.get("password") or ""
        device_uid = (payload.get("device_uid") or "").strip()
        device_name = (payload.get("device_name") or "").strip()
        platform = (payload.get("platform") or "").strip()
        manufacturer = (payload.get("manufacturer") or "").strip()
        model_name = (payload.get("model_name") or "").strip()
        app_version = (payload.get("app_version") or "").strip()
        ip_address = (payload.get("ip_address") or self._client_ip() or "").strip()

        _logger.info(
            "Employee App login request received: login=%s device_uid=%s device_name=%s ip=%s has_json=%s",
            login_name,
            device_uid,
            device_name,
            ip_address,
            bool(request.httprequest.is_json),
        )

        if not login_name or not password:
            _logger.warning("Mobile login rejected: missing login/password login=%s", login_name)
            return request.make_json_response(
                {"error": "invalid_request", "message": _("login and password are required.")},
                status=400,
            )
        if not device_uid:
            _logger.warning("Mobile login rejected: missing device_uid login=%s", login_name)
            return request.make_json_response(
                {"error": "invalid_request", "message": _("device_uid is required.")},
                status=400,
            )

        wsgienv = {
            "interactive": False,
            "base_location": request.httprequest.url_root.rstrip("/"),
            "HTTP_HOST": request.httprequest.environ.get("HTTP_HOST", ""),
            "REMOTE_ADDR": request.httprequest.environ.get("REMOTE_ADDR", ""),
        }
        credential = {"type": "password", "login": login_name, "password": password}
        try:
            auth_info = request.env["res.users"].sudo().authenticate(credential, wsgienv)
        except AccessDenied:
            _logger.warning("Mobile login access denied: login=%s", login_name)
            return request.make_json_response(
                {"error": "access_denied", "message": _("Invalid login or password.")},
                status=401,
            )

        uid = auth_info["uid"]
        user = request.env["res.users"].sudo().browse(uid)
        if not self._eligible_mobile_user(user):
            _logger.warning("Mobile login forbidden by group eligibility: user_id=%s login=%s", user.id, login_name)
            return request.make_json_response(
                {"error": "forbidden", "message": _("This user cannot use the mobile login.")},
                status=403,
            )

        try:
            token_info = request.env["anabtawi.mobile.device"].register_or_refresh_login(
                user, device_uid, device_name, ip_address=ip_address, platform=platform, manufacturer=manufacturer, model_name=model_name, app_version=app_version
            )
        except UserError as e:
            _logger.warning(
                "Mobile login rejected by device policy: user_id=%s login=%s device_uid=%s reason=%s",
                user.id,
                login_name,
                device_uid,
                e.args[0] if e.args else "unknown",
                )
            return request.make_json_response(
                {"error": "DEVICE_ALREADY_REGISTERED", "message": e.args[0]},
                status=403,
            )

        _logger.info("Mobile login success: user_id=%s login=%s device_uid=%s", user.id, login_name, device_uid)
        return request.make_json_response({
            "status": "ok",
            "uid": user.id,
            "login": user.login,
            "access_token": token_info["access_token"],
        }, status=200)

    @http.route(
        "/anabtawi/mobile/auth/me",
        type="http", auth="public", methods=["GET", "POST"], csrf=False,
    )
    def mobile_me(self, **kwargs):
        auth_header = request.httprequest.headers.get("Authorization", "")
        plain = _parse_bearer(auth_header)
        user = request.env["anabtawi.mobile.device"].authenticate_bearer_token(plain, ip_address=self._client_ip()) if plain else request.env["res.users"]

        if not user:
            return request.make_json_response(
                {"error": "unauthorized", "message": _("Invalid or missing token.")},
                status=401,
            )

        u = user.with_user(user)
        return request.make_json_response({
            "status": "ok",
            "uid": user.id,
            "login": user.login,
            "is_portal": bool(u.has_group("base.group_portal")),
            "is_internal": bool(u.has_group("base.group_user")),
        }, status=200)

    @http.route(
        "/anabtawi/mobile/ping",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def mobile_ping(self, **kwargs):
        auth_header = request.httprequest.headers.get("Authorization", "")
        plain = _parse_bearer(auth_header)
        user = request.env["anabtawi.mobile.device"].authenticate_bearer_token(plain, ip_address=self._client_ip()) if plain else request.env["res.users"]
        if not user:
            return request.make_json_response({"error": "unauthorized"}, status=401)
        return request.make_json_response({
            "status": "ok",
            "message": "authenticated",
            "uid": user.id,
        }, status=200)

    def _authenticated_user(self):
        token = _parse_bearer(request.httprequest.headers.get("Authorization"))
        if not token:
            return None, None, _error("unauthorized", _("Authentication is required."), 401)
        user = request.env["anabtawi.mobile.device"].authenticate_bearer_token(token, ip_address=self._client_ip())
        if not user:
            return None, token, _error("session_expired", _("Your session has expired."), 401)
        return user, token, None

    def _employee(self, user):
        return request.env["hr.employee"].sudo().search([
            ("user_id", "=", user.id),
            ("active", "=", True),
        ], limit=1)

    def _require_employee(self):
        user, token, error = self._authenticated_user()
        if error:
            return None, None, None, error
        employee = self._employee(user)
        if not employee:
            return None, user, token, _error(
                "employee_not_found", _("No active employee is linked to this user."), 404
            )
        return employee, user, token, None


    @http.route(
        "/anabtawi/mobile/auth/change-password",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def change_password(self, **kwargs):
        user, _token, error = self._authenticated_user()
        if error:
            return error
        data = _payload()
        current_password = data.get("current_password") or data.get("old_password") or ""
        new_password = data.get("new_password") or ""
        confirm_password = data.get("confirm_password") or ""

        if not current_password or not new_password or not confirm_password:
            return _error("invalid_request", _("Current password, new password, and confirmation are required."), 400)
        if new_password != confirm_password:
            return _error("password_mismatch", _("The new password and confirmation do not match."), 422)
        if len(new_password) < 8:
            return _error("weak_password", _("The new password must be at least 8 characters."), 422)
        if current_password == new_password:
            return _error("same_password", _("The new password must be different from the current password."), 422)

        wsgienv = {
            "interactive": False,
            "base_location": request.httprequest.url_root.rstrip("/"),
            "HTTP_HOST": request.httprequest.environ.get("HTTP_HOST", ""),
            "REMOTE_ADDR": request.httprequest.environ.get("REMOTE_ADDR", ""),
        }
        credential = {"type": "password", "login": user.login, "password": current_password}
        try:
            auth_info = request.env["res.users"].sudo().authenticate(credential, wsgienv)
        except AccessDenied:
            return _error("invalid_current_password", _("The current password is incorrect."), 401)
        except Exception:
            _logger.exception("Password verification failed for user_id=%s", user.id)
            return _error("server_error", _("The current password could not be verified."), 500)

        if not auth_info or auth_info.get("uid") != user.id:
            return _error("invalid_current_password", _("The current password is incorrect."), 401)

        try:
            user.sudo().write({"password": new_password})
        except Exception:
            _logger.exception("Password update failed for user_id=%s", user.id)
            return _error("server_error", _("The password could not be changed."), 500)

        return _json({"status": "ok", "success": True, "message": _("Password changed successfully.")}, 200)

    @http.route(
        "/anabtawi/mobile/auth/logout",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def logout(self, **kwargs):
        user, token, error = self._authenticated_user()
        if error:
            return error
        request.env["anabtawi.mobile.device"].revoke_bearer_token(token)
        return _json({"status": "ok", "uid": user.id})

    @http.route(
        "/anabtawi/mobile/employee/profile",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def employee_profile(self, **kwargs):
        employee, user, _token, error = self._require_employee()
        if error:
            return error
        work_location = employee.work_location_id
        otp_number = ""
        otp_expires_at = None
        otp_expires_in_seconds = 0
        now = fields.Datetime.now()
        if "employee_password" in employee._fields and employee.employee_password:
            expires_at = employee.employee_password_expires_at if "employee_password_expires_at" in employee._fields else False
            if not expires_at or expires_at > now:
                otp_number = str(employee.employee_password)
                otp_expires_at = fields.Datetime.to_string(expires_at) if expires_at else None
                if expires_at:
                    otp_expires_in_seconds = max(0, int((expires_at - now).total_seconds()))
        if not otp_number:
            for field_name in ("otp_number", "employee_otp", "otp", "pin"):
                if field_name in employee._fields and employee[field_name]:
                    otp_number = str(employee[field_name])
                    break
        return _json({
            "status": "ok",
            "uid": user.id,
            "employee_id": employee.id,
            "login": user.login,
            "name": employee.name,
            "job_title": employee.job_title or "",
            "department_name": employee.department_id.name if employee.department_id else "",
            "work_location": work_location.name if work_location else "",
            "mobile_phone": employee.mobile_phone or "",
            "otp_number": otp_number,
            "employee_otp": otp_number,
            "otp_source": "employee_request.hr.employee.employee_password" if "employee_password" in employee._fields else "hr.employee",
            "otp_expires_at": otp_expires_at,
            "otp_expires_in_seconds": otp_expires_in_seconds,
            "company_name": employee.company_id.name,
            "geo_required": employee._is_portal_geo_tracking_required(),
            "allow_remote": bool(employee.allow_remote_attendance),
            "device": {
                "device_uid": employee.employee_app_device_uid or "",
                "device_name": employee.employee_app_device_name or "",
                "platform": employee.employee_app_platform or "",
                "manufacturer": employee.employee_app_manufacturer or "",
                "model_name": employee.employee_app_model_name or "",
                "app_version": employee.employee_app_version or "",
                "registered_ip": employee.employee_app_registered_ip or "",
                "last_ip": employee.employee_app_last_ip or "",
                "registered_at": fields.Datetime.to_string(employee.employee_app_registered_at) if employee.employee_app_registered_at else None,
                "last_login": fields.Datetime.to_string(employee.employee_app_last_login) if employee.employee_app_last_login else None,
            },
        })

    @http.route(
        "/anabtawi/mobile/employee/otp/generate",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def employee_generate_otp(self, **kwargs):
        employee, user, _token, error = self._require_employee()
        if error:
            return error
        if not hasattr(employee, "action_generate_employee_portal_otp"):
            return _error("otp_not_available", _("Employee OTP generation is not installed."), 501)
        result = employee.sudo().action_generate_employee_portal_otp()
        otp = result.get("employee_otp") or result.get("otp_number") or ""
        return _json({
            "status": "ok",
            "success": True,
            "uid": user.id,
            "employee_id": employee.id,
            "employee_otp": otp,
            "otp_number": otp,
            "otp_expires_at": result.get("otp_expires_at"),
            "expires_in_seconds": result.get("expires_in_seconds", 300),
        })

    def _today_bounds_utc(self, employee):
        tz_name = (
            employee._get_attendance_timezone()
            if hasattr(type(employee), "_get_attendance_timezone")
            else (employee.tz or "UTC")
        )
        try:
            timezone = pytz.timezone(tz_name or "UTC")
        except pytz.UnknownTimeZoneError:
            timezone = pytz.UTC
        today = datetime.now(timezone).date()
        start = timezone.localize(datetime.combine(today, time.min)).astimezone(pytz.UTC)
        end = timezone.localize(datetime.combine(today, time.max)).astimezone(pytz.UTC)
        return start.replace(tzinfo=None), end.replace(tzinfo=None)

    @http.route(
        "/anabtawi/mobile/attendance/status",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def attendance_status(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error
        start_utc, end_utc = self._today_bounds_utc(employee)
        records = request.env["hr.attendance"].sudo().search([
            ("employee_id", "=", employee.id),
            ("check_in", ">=", start_utc),
            ("check_in", "<=", end_utc),
        ])
        open_attendance = records.filtered(lambda attendance: not attendance.check_out)[:1]
        if not open_attendance:
            open_attendance = request.env["hr.attendance"].sudo().search([
                ("employee_id", "=", employee.id),
                ("check_out", "=", False),
            ], limit=1)
        return _json({
            "status": "ok",
            "attendance_state": employee.attendance_state,
            "today_worked_hours": round(sum(records.mapped("worked_hours")), 2),
            "geo_required": employee._is_portal_geo_tracking_required(),
            "allow_remote": bool(employee.allow_remote_attendance),
            "open_attendance_id": open_attendance.id or None,
        })

    @http.route(
        "/anabtawi/mobile/attendance/action",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def attendance_action(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error
        data = _payload()
        latitude = _as_float(data.get("latitude"))
        longitude = _as_float(data.get("longitude"))
        accuracy = _as_float(data.get("accuracy"))
        geo_information = None
        if latitude is not None and longitude is not None:
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return _error("invalid_location", _("Invalid GPS coordinates."), 422)
            geo_information = {"latitude": latitude, "longitude": longitude}

        if employee.attendance_state != "checked_in" and employee._is_portal_geo_tracking_required():
            max_accuracy = _as_float(
                request.env["ir.config_parameter"].sudo().get_param(
                    "anabtawi_mobile.max_location_accuracy_m", "100"
                )
            ) or 100.0
            if accuracy is None or accuracy < 0 or accuracy > max_accuracy:
                return _error(
                    "location_accuracy",
                    _("A more accurate GPS location is required. Move outdoors and try again."),
                    422,
                )

        lock_acquired = False
        try:
            employee._acquire_portal_attendance_action_lock(lock_minutes=10)
            lock_acquired = True
            attendance = employee._attendance_action_change(geo_information=geo_information)
        except (UserError, ValidationError) as exc:
            if lock_acquired:
                employee._release_portal_attendance_action_lock()
            message = exc.args[0] if exc.args else str(exc)
            code = "attendance_locked" if "10" in message or "wait" in message.lower() else "attendance_rejected"
            return _error(code, message, 429 if code == "attendance_locked" else 422)
        except Exception:
            if lock_acquired:
                employee._release_portal_attendance_action_lock()
            _logger.exception("Mobile attendance failed for employee_id=%s", employee.id)
            return _error("server_error", _("Attendance could not be saved."), 500)

        employee.invalidate_recordset(["attendance_state"])
        return _json({
            "status": "ok",
            "action": "check_in" if employee.attendance_state == "checked_in" else "check_out",
            "attendance_state": employee.attendance_state,
            "check_in": fields.Datetime.to_string(attendance.check_in) if attendance.check_in else None,
            "check_out": fields.Datetime.to_string(attendance.check_out) if attendance.check_out else None,
            "worked_hours": round(attendance.worked_hours or 0.0, 2),
        })

    @http.route(
        "/anabtawi/mobile/attendance/history",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def attendance_history(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error
        records = request.env["hr.attendance"].sudo().search(
            [("employee_id", "=", employee.id)], order="check_in desc", limit=30
        )
        return _json({"status": "ok", "records": [{
            "id": record.id,
            "check_in": fields.Datetime.to_string(record.check_in) if record.check_in else None,
            "check_out": fields.Datetime.to_string(record.check_out) if record.check_out else None,
            "worked_hours": round(record.worked_hours or 0.0, 2),
        } for record in records]})

    def _eligible_leave_types(self, employee):
        LeaveType = request.env["hr.leave.type"].sudo().with_company(
            employee.company_id
        ).with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            allowed_company_ids=[employee.company_id.id],
        )
        domain = [
            ("active", "=", True),
            ("time_type", "=", "leave"),
            ("company_id", "in", [False, employee.company_id.id]),
            ("country_id", "in", [False, employee.company_id.country_id.id]),
            "|", ("requires_allocation", "=", False), ("has_valid_allocation", "=", True),
        ]
        return LeaveType.search(domain, order="sequence, id")

    @http.route(
        "/anabtawi/mobile/leaves/balances",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def leave_balances(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error
        leave_types = self._eligible_leave_types(employee)
        allocation_rows = leave_types.get_allocation_data(employee).get(employee, [])
        allocation_by_id = {row[3]: row[1] for row in allocation_rows}
        return _json({"status": "ok", "leave_types": [{
            "id": leave_type.id,
            "name": leave_type.name,
            "max_leaves": round(allocation_by_id.get(leave_type.id, {}).get("max_leaves", 0.0), 2),
            "leaves_used": round(allocation_by_id.get(leave_type.id, {}).get("leaves_taken", 0.0), 2),
            "remaining": round(allocation_by_id.get(leave_type.id, {}).get("virtual_remaining_leaves", 0.0), 2),
            "request_unit": leave_type.request_unit,
            "requires_allocation": bool(leave_type.requires_allocation),
        } for leave_type in leave_types]})

    @http.route(
        "/anabtawi/mobile/leaves/create",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def leave_create(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error
        data = _payload()
        try:
            type_id = int(data.get("holiday_status_id") or 0)
            date_from = fields.Date.to_date(data.get("request_date_from"))
            date_to = fields.Date.to_date(data.get("request_date_to"))
        except (TypeError, ValueError):
            return _error("invalid_request", _("Valid leave type and dates are required."), 422)
        if not date_from or not date_to or date_to < date_from:
            return _error("invalid_dates", _("The end date must be on or after the start date."), 422)
        leave_type = self._eligible_leave_types(employee).filtered(lambda item: item.id == type_id)
        if not leave_type:
            return _error("invalid_leave_type", _("This time off type is not available."), 422)
        reason = (data.get("name") or "").strip()
        if not reason:
            return _error("invalid_request", _("A reason is required."), 422)

        vals = {
            "employee_id": employee.id,
            "holiday_status_id": leave_type.id,
            "request_date_from": date_from,
            "request_date_to": date_to,
            "name": reason,
        }
        if bool(data.get("request_unit_hours")):
            hour_from = _as_float(data.get("request_hour_from"))
            hour_to = _as_float(data.get("request_hour_to"))
            if leave_type.request_unit != "hour":
                return _error(
                    "hourly_leave_type_required",
                    _("This time off type must use the Hours request unit."),
                    422,
                )
            if date_from != date_to:
                return _error("invalid_hourly_leave", _("An hourly request must use one date."), 422)
            if hour_from is None or hour_to is None or hour_from < 0 or hour_to > 24 or hour_to <= hour_from:
                return _error(
                    "invalid_leave_time",
                    _("Enter a valid start and end time; the end must be after the start."),
                    422,
                )
            vals.update({
                "request_unit_hours": True,
                "request_hour_from": hour_from,
                "request_hour_to": hour_to,
            })
        if bool(data.get("request_unit_half")):
            if date_from != date_to:
                return _error("invalid_half_day", _("A half-day request must use one date."), 422)
            vals.update({
                "request_unit_half": True,
                "request_date_from_period": data.get("request_date_from_period") if data.get("request_date_from_period") in ("am", "pm") else "am",
            })
        try:
            with request.env.cr.savepoint():
                leave = request.env["hr.leave"].sudo().with_company(employee.company_id).create(vals)
        except (UserError, ValidationError) as exc:
            return _error("validation_error", exc.args[0] if exc.args else str(exc), 422)
        except Exception:
            _logger.exception("Mobile leave creation failed for employee_id=%s", employee.id)
            return _error("server_error", _("The time off request could not be saved."), 500)
        return _json({"status": "ok", "leave_id": leave.id, "state": leave.state}, 201)

    @http.route(
        "/anabtawi/mobile/leaves/list",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def leave_list(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error
        leaves = request.env["hr.leave"].sudo().search(
            [("employee_id", "=", employee.id)], order="request_date_from desc, id desc", limit=30
        )
        return _json({"status": "ok", "records": [{
            "id": leave.id,
            "name": leave.name or "",
            "type": leave.holiday_status_id.name,
            "date_from": fields.Date.to_string(leave.request_date_from) if leave.request_date_from else None,
            "date_to": fields.Date.to_string(leave.request_date_to) if leave.request_date_to else None,
            "hour_from": round(leave.request_hour_from, 4) if leave.request_unit_hours else None,
            "hour_to": round(leave.request_hour_to, 4) if leave.request_unit_hours else None,
            "days": round(leave.number_of_days or 0.0, 2),
            "state": leave.state,
        } for leave in leaves]})

    def _overtime_feature_disabled(self):
        return _error(
            "feature_disabled",
            _("Overtime approval requests are no longer available."),
            410,
        )

    @http.route(
        "/anabtawi/mobile/overtime/categories",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def overtime_categories(self, **kwargs):
        return self._overtime_feature_disabled()

    @http.route(
        "/anabtawi/mobile/overtime/create",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def overtime_create(self, **kwargs):
        return self._overtime_feature_disabled()

    @http.route(
        "/anabtawi/mobile/overtime/list",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def overtime_list(self, **kwargs):
        return self._overtime_feature_disabled()


    @http.route(
        "/anabtawi/mobile/payslips/list",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def payslip_list(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error

        records = request.env["hr.payslip"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("state", "in", ["done", "paid"]),
            ],
            order="date_to desc, id desc",
            limit=50,
        )

        return _json({
            "status": "ok",
            "records": [
                {
                    "id": payslip.id,
                    "number": payslip.number or f"PAY/{payslip.id}",
                    "name": payslip.name or _("Payslip"),
                    "date_from": fields.Date.to_string(payslip.date_from) if payslip.date_from else None,
                    "date_to": fields.Date.to_string(payslip.date_to) if payslip.date_to else None,
                    "net_wage": round(payslip.net_wage or 0.0, 2) if hasattr(payslip, "net_wage") else 0.0,
                    "basic_wage": round(payslip.basic_wage or 0.0, 2) if hasattr(payslip, "basic_wage") else 0.0,
                    "state": payslip.state,
                }
                for payslip in records
            ],
        })

    @http.route(
        "/anabtawi/mobile/payslips/download",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def payslip_download(self, **kwargs):
        employee, _user, _token, error = self._require_employee()
        if error:
            return error

        data = _payload()
        try:
            payslip_id = int(kwargs.get("id") or data.get("id") or 0)
        except (TypeError, ValueError):
            return _error("invalid_request", _("Valid payslip ID is required."), 400)

        if not payslip_id:
            return _error("invalid_request", _("Valid payslip ID is required."), 400)

        payslip = request.env["hr.payslip"].sudo().search(
            [
                ("id", "=", payslip_id),
                ("employee_id", "=", employee.id),
                ("state", "in", ["done", "paid"]),
            ],
            limit=1,
        )

        if not payslip:
            return _error("not_found", _("Payslip not found or access denied."), 404)

        try:
            report_name = "hr_payroll.report_payslip"
            pdf_content, _format = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
                report_name, [payslip.id]
            )
        except Exception:
            _logger.exception("Failed to render PDF for payslip_id=%s", payslip.id)
            return _error("pdf_failed", _("Could not generate payslip PDF."), 500)

        filename = f"Payslip_{payslip.number or payslip.id}.pdf"
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Length", str(len(pdf_content))),
        ]
        return request.make_response(pdf_content, headers=headers)

    @http.route(
        "/anabtawi/mobile/app/check_update",
        type="http", auth="public", methods=["GET"], csrf=False, sitemap=False,
    )
    def check_app_update(self, **kwargs):
        config = request.env["ir.config_parameter"].sudo()
        latest_version = config.get_param("anabtawi_mobile.latest_version")
        if not latest_version:
            config.set_param("anabtawi_mobile.latest_version", "1.2.0")
            latest_version = "1.2.0"

        min_version = config.get_param("anabtawi_mobile.min_version", "1.0.0")
        update_message = config.get_param(
            "anabtawi_mobile.update_message",
            _("A new version of the Anabtawi Employee App (v1.2.0) with Payslip support is available. Please update to continue.")
        )
        download_url = config.get_param(
            "anabtawi_mobile.download_url",
            "/anabtawi/mobile/apk/download"
        )
        force_update = config.get_param("anabtawi_mobile.force_update", "False").lower() in ("true", "1", "yes")

        return _json({
            "status": "ok",
            "latest_version": latest_version,
            "min_version": min_version,
            "update_message": update_message,
            "download_url": download_url,
            "force_update": force_update,
        })

    @http.route(
        "/anabtawi/mobile/apk/download",
        type="http", auth="public", methods=["GET"], csrf=False, sitemap=False,
    )
    def apk_download(self, **kwargs):
        module_path = os.path.dirname(os.path.dirname(__file__))
        apk_path = os.path.join(module_path, "static", "apk", "employee_app_latest.apk")
        if not os.path.exists(apk_path):
            return request.make_response("APK file not found on server.", status=404)

        with open(apk_path, "rb") as file:
            apk_bytes = file.read()

        filename = "Employee-App-v1.2.0-with-payslip.apk"
        headers = [
            ("Content-Type", "application/vnd.android.package-archive"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Length", str(len(apk_bytes))),
            ("Cache-Control", "no-cache"),
        ]
        return request.make_response(apk_bytes, headers=headers)

    @http.route(["/pwa", "/mobile/app"], type="http", auth="public", csrf=False)
    def pwa_index(self, **kwargs):
        pwa_path = os.path.join(os.path.dirname(__file__), "../static/pwa/index.html")
        if os.path.exists(pwa_path):
            with open(pwa_path, "r", encoding="utf-8") as f:
                content = f.read()
            return request.make_response(content, [("Content-Type", "text/html; charset=utf-8")])
        return _error("not_found", _("PWA application files not found."), 404)