# -*- coding: utf-8 -*-

import odoo
import odoo.exceptions
from odoo import http
from odoo.addons.web.controllers.home import (
    CREDENTIAL_PARAMS,
    SIGN_UP_REQUEST_PARAMS,
    Home,
    ensure_db,
)
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools.translate import _

ACTING_LOGIN_PARAMS = {'acting_employee_number', 'acting_employee_password'}


class ActingEmployeeHome(Home):

    def _store_acting_employee_session(self, employee):
        request.session['acting_employee_id'] = employee.id
        request.session['acting_employee_name'] = employee.name

    def _clear_acting_employee_session(self):
        request.session.pop('acting_employee_id', None)
        request.session.pop('acting_employee_name', None)

    def _login_error_values(self, error_message):
        values = {
            k: v
            for k, v in request.params.items()
            if k in SIGN_UP_REQUEST_PARAMS | ACTING_LOGIN_PARAMS
        }
        try:
            values['databases'] = http.db_list()
        except AccessDenied:
            values['databases'] = None
        values['error'] = error_message
        if 'login' not in values and request.session.get('auth_login'):
            values['login'] = request.session.get('auth_login')
        if not odoo.tools.config['list_db']:
            values['disable_database_manager'] = True
        return values

    @http.route()
    def web_login(self, redirect=None, **kw):
        if request.httprequest.method != 'POST':
            return super().web_login(redirect=redirect, **kw)

        ensure_db()
        request.params['login_success'] = False

        if request.env.uid is None:
            if request.session.uid is None:
                request.env['ir.http']._auth_method_public()
            else:
                request.update_env(user=request.session.uid)

        try:
            credential = {
                key: value
                for key, value in request.params.items()
                if key in CREDENTIAL_PARAMS and value
            }
            credential.setdefault('type', 'password')
            if request.env['res.users']._should_captcha_login(credential):
                request.env['ir.http']._verify_request_recaptcha_token('login')

            auth_info = request.session.authenticate(request.env, credential)
            request.update_env(user=auth_info['uid'])

            user = request.env['res.users'].browse(auth_info['uid'])
            employee = request.env['hr.employee']._authenticate_acting_employee(
                request.params.get('acting_employee_number'),
                request.params.get('acting_employee_password'),
                user=user,
            )
            self._store_acting_employee_session(employee)

            request.params['login_success'] = True
            return request.redirect(
                self._login_redirect(auth_info['uid'], redirect=redirect)
            )
        except AccessDenied as exc:
            self._clear_acting_employee_session()
            request.session.logout(keep_db=True)
            if request.env.uid:
                request.env['ir.http']._auth_method_public()
            if exc.args == AccessDenied().args:
                error_message = _('Wrong login/password')
            else:
                error_message = exc.args[0]
            values = self._login_error_values(error_message)

        response = request.render('web.login', values)
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response
