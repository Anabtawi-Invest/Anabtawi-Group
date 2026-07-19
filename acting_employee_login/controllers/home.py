# -*- coding: utf-8 -*-

import odoo
from odoo import http
from odoo.addons.web.controllers.home import SIGN_UP_REQUEST_PARAMS, ensure_db
from odoo.addons.website.controllers.main import Website
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools.translate import _

ACTING_LOGIN_PARAMS = {'acting_employee_name', 'acting_employee_password'}


class ActingEmployeeHome(Website):
    """Extend website login: validate acting employee before user auth."""

    def _store_acting_employee_session(self, employee):
        request.session['acting_employee_id'] = employee.id
        request.session['acting_employee_name'] = employee.name

    def _render_acting_login_error(self, error_message):
        """Render login form with an error without touching the session."""
        ensure_db()
        if request.env.uid is None:
            request.env['ir.http']._auth_method_public()

        values = {
            k: v
            for k, v in request.params.items()
            if k in SIGN_UP_REQUEST_PARAMS | ACTING_LOGIN_PARAMS
        }
        values['error'] = error_message
        try:
            values['databases'] = http.db_list()
        except AccessDenied:
            values['databases'] = None
        if 'login' not in values and request.session.get('auth_login'):
            values['login'] = request.session.get('auth_login')
        if not odoo.tools.config['list_db']:
            values['disable_database_manager'] = True
        if hasattr(self, 'get_auth_signup_config'):
            values.update(self.get_auth_signup_config())

        response = request.render('web.login', values)
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    # Keep website=True + auth='public' so CSRF/session match the login page.
    @http.route(website=True, auth='public', sitemap=False)
    def web_login(self, *args, **kw):
        ensure_db()
        pending_employee = None

        if request.httprequest.method == 'POST':
            # Validate employee BEFORE authenticate() so the session is not
            # rotated then cleared (that mismatch causes invalid CSRF token).
            try:
                pending_employee = request.env['hr.employee'].sudo()._authenticate_acting_employee(
                    request.params.get('acting_employee_name'),
                    request.params.get('acting_employee_password'),
                )
            except AccessDenied as exc:
                if exc.args == AccessDenied().args:
                    error_message = _('Wrong employee name or employee password.')
                else:
                    error_message = exc.args[0]
                return self._render_acting_login_error(error_message)

        response = super().web_login(*args, **kw)

        if pending_employee and request.session.uid:
            self._store_acting_employee_session(pending_employee)

        return response
