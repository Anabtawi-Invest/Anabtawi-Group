# -*- coding: utf-8 -*-

from odoo import models
from odoo.http import request


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _is_acting_employee_web_login(self):
        """True when credentials come from the /web/login form POST."""
        if not request or not getattr(request, 'httprequest', None):
            return False
        if request.httprequest.method != 'POST':
            return False
        path = request.httprequest.path or ''
        return path.rstrip('/') == '/web/login'

    def _authenticate_acting_employee_from_request(self):
        """Validate acting employee fields from the login form, or raise."""
        return self.env['hr.employee'].sudo()._authenticate_acting_employee(
            request.params.get('acting_employee_name'),
            request.params.get('acting_employee_password'),
        )

    @staticmethod
    def _store_acting_employee_session(employee):
        if not request or not getattr(request, 'session', None):
            return
        request.session['acting_employee_id'] = employee.id
        request.session['acting_employee_name'] = employee.name

    def authenticate(self, credential, user_agent_env):
        # Validate acting employee BEFORE parent auth so a failed check never
        # rotates/finalizes the session (that caused invalid CSRF on re-login).
        employee = None
        if self._is_acting_employee_web_login():
            employee = self._authenticate_acting_employee_from_request()

        auth_info = super().authenticate(credential, user_agent_env)

        if employee:
            self._store_acting_employee_session(employee)
        return auth_info
