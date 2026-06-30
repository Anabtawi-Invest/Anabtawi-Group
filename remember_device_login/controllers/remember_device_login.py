# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request
from odoo.service import security
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.session import Session

_logger = logging.getLogger(__name__)


def _parse_bearer(header_value):
    if not header_value:
        return None
    parts = header_value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


class RememberDeviceHome(Home):
    def _remember_model(self):
        return request.env["remember.device.token"].sudo()

    def _device_fingerprint(self):
        user_agent = (request.httprequest.user_agent.string or "").strip()
        return user_agent[:512]

    def _set_remember_cookie(self, response, user):
        model = self._remember_model()
        plain = model.issue_for_user(user, self._device_fingerprint())
        response.set_cookie(
            model._cookie_name(),
            plain,
            max_age=model._cookie_max_age(),
            httponly=True,
            secure=bool(request.httprequest.is_secure),
            samesite="Lax",
            path="/",
        )

    def _login_with_user(self, user):
        request.session.uid = user.id
        request.session.db = request.db
        request.update_env(user=user.id)
        request.session.session_token = security.compute_session_token(request.session, request.env)

    def _try_cookie_autologin(self):
        if request.session.uid:
            return False
        model = self._remember_model()
        plain = request.httprequest.cookies.get(model._cookie_name())
        if not plain:
            return False
        user = model.authenticate_cookie(plain, self._device_fingerprint())
        if not user:
            return False
        self._login_with_user(user)
        _logger.info("remember_device_login auto-login success: user_id=%s", user.id)
        return True

    @http.route()
    def web_login(self, redirect=None, **kw):
        # Attempt auto-login from remember cookie before rendering login page.
        if request.httprequest.method == "GET":
            try:
                if self._try_cookie_autologin():
                    return request.redirect(redirect or "/odoo")
            except Exception:
                # Never block /web/login due to remember-device side effects.
                _logger.exception("remember_device_login auto-login failed; fallback to standard login flow")

        response = super().web_login(redirect=redirect, **kw)

        # On successful credential login, create remember cookie.
        if request.params.get("login_success") and request.session.uid:
            try:
                self._set_remember_cookie(response, request.env.user)
            except Exception:
                # Successful login must not fail if trusted-device persistence fails.
                _logger.exception("remember_device_login cookie issue failed; login kept successful")
        return response

    @http.route("/anabtawi/remember/bootstrap", type="http", auth="public", methods=["POST"], csrf=False)
    def remember_bootstrap(self, **kwargs):
        del kwargs
        auth_header = request.httprequest.headers.get("Authorization", "")
        plain = _parse_bearer(auth_header)
        user = request.env["res.users"]
        if plain and "anabtawi.mobile.device" in request.env:
            user = request.env["anabtawi.mobile.device"].sudo().authenticate_bearer_token(plain)
        if not user:
            return request.make_json_response({"status": "unauthorized"}, status=401)

        self._login_with_user(user)
        response = request.make_json_response({"status": "ok", "uid": user.id}, status=200)
        self._set_remember_cookie(response, user)
        return response


class RememberDeviceSession(Session):
    @http.route()
    def logout(self, redirect="/odoo"):
        response = super().logout(redirect=redirect)
        model = request.env["remember.device.token"].sudo()
        plain = request.httprequest.cookies.get(model._cookie_name())
        if plain:
            model.revoke_cookie(plain)
        response.delete_cookie(model._cookie_name(), path="/")
        return response
