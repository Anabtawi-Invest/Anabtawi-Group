# -*- coding: utf-8 -*-

import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _is_acting_employee_web_login(self):
        """True when the login form posted acting-employee fields."""
        if not request or not getattr(request, 'httprequest', None):
            return False
        if request.httprequest.method != 'POST':
            return False
        # Prefer param presence over path matching (website may use lang prefixes).
        return (
            'acting_employee_name' in request.params
            or 'acting_employee_password' in request.params
        )

    def _authenticate_acting_employee_from_request(self):
        """Validate acting employee fields from the login form, or raise."""
        name = request.params.get('acting_employee_name')
        _logger.warning(
            "acting_employee_login auth: validating acting employee name=%r "
            "has_password=%s session_uid=%s sid_prefix=%s",
            (name or '')[:80],
            bool(request.params.get('acting_employee_password')),
            request.session.uid if request.session else None,
            (request.session.sid or '')[:12] if request.session else None,
        )
        return self.env['hr.employee'].sudo()._authenticate_acting_employee(
            name,
            request.params.get('acting_employee_password'),
        )

    @staticmethod
    def _store_acting_employee_session(employee):
        if not request or not getattr(request, 'session', None):
            return
        request.session['acting_employee_id'] = employee.id
        request.session['acting_employee_name'] = employee.name
        _logger.warning(
            "acting_employee_login auth: stored acting employee in session "
            "employee_id=%s name=%r",
            employee.id,
            employee.name,
        )

    def authenticate(self, credential, user_agent_env):
        # Validate acting employee BEFORE parent auth so a failed check never
        # rotates/finalizes the session (that caused invalid CSRF on re-login).
        employee = None
        is_acting_login = self._is_acting_employee_web_login()
        _logger.warning(
            "acting_employee_login auth: authenticate called login=%r "
            "is_acting_login=%s interactive=%s",
            (credential or {}).get('login'),
            is_acting_login,
            (user_agent_env or {}).get('interactive'),
        )
        if is_acting_login:
            employee = self._authenticate_acting_employee_from_request()

        auth_info = super().authenticate(credential, user_agent_env)

        if employee:
            self._store_acting_employee_session(employee)
        return auth_info
