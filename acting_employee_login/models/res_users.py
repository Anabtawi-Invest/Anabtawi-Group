# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_branch_user = fields.Boolean(
        string='Is Branch User',
        help='If enabled, the second login step validates a branch name and '
             'password assigned to this user under Inventory > Branch Login Access.',
    )

    acting_branch_access_ids = fields.One2many(
        'acting.branch.access',
        'user_id',
        string='Branch Login Access',
    )

    def _is_second_step_web_login(self):
        """True when the login form posted the second-step fields."""
        if not request or not getattr(request, 'httprequest', None):
            return False
        if request.httprequest.method != 'POST':
            return False
        return (
            'acting_employee_number' in request.params
            or 'acting_employee_password' in request.params
        )

    @api.model
    def _lookup_user_by_login(self, login):
        login = (login or '').strip()
        if not login:
            return self.env['res.users']
        return self.sudo().search(
            self._get_login_domain(login),
            order=self._get_login_order(),
            limit=1,
        )

    def _authenticate_second_step_from_request(self, login):
        """Validate employee or branch credentials before session auth."""
        second_step_id = request.params.get('acting_employee_number')
        password = request.params.get('acting_employee_password')
        user = self._lookup_user_by_login(login)

        if user and user.is_branch_user:
            _logger.warning(
                "acting_employee_login auth: validating branch access login=%r "
                "user_id=%s is_branch_user=%s branch_name=%r has_password=%s",
                login,
                user.id,
                user.is_branch_user,
                (second_step_id or '')[:80],
                bool(password),
            )
            return self.env['acting.branch.access']._authenticate_branch_access(
                user, second_step_id, password
            )

        _logger.warning(
            "acting_employee_login auth: validating acting employee login=%r "
            "user_id=%s is_branch_user=%s employee_number=%r has_password=%s",
            login,
            user.id if user else None,
            user.is_branch_user if user else None,
            (second_step_id or '')[:80],
            bool(password),
        )
        return self.env['hr.employee'].sudo()._authenticate_acting_employee(
            second_step_id, password, user=user
        )

    @staticmethod
    def _clear_acting_session():
        if not request or not getattr(request, 'session', None):
            return
        for key in (
            'acting_employee_id',
            'acting_employee_name',
            'acting_branch_access_id',
            'acting_branch_name',
        ):
            request.session.pop(key, None)

    @staticmethod
    def _store_acting_employee_session(employee):
        if not request or not getattr(request, 'session', None):
            return
        ResUsers._clear_acting_session()
        request.session['acting_employee_id'] = employee.id
        request.session['acting_employee_name'] = employee.name
        request.session.touch()
        _logger.warning(
            "acting_employee_login auth: stored acting employee employee_id=%s name=%r",
            employee.id,
            employee.name,
        )

    @staticmethod
    def _store_branch_access_session(access):
        if not request or not getattr(request, 'session', None):
            return
        ResUsers._clear_acting_session()
        request.session['acting_branch_access_id'] = access.id
        request.session['acting_branch_name'] = access.branch_name
        request.session.touch()
        _logger.warning(
            "acting_employee_login auth: stored branch access access_id=%s branch_name=%r",
            access.id,
            access.branch_name,
        )

    def authenticate(self, credential, user_agent_env):
        second_step_identity = None
        is_second_step = self._is_second_step_web_login()
        login = (credential or {}).get('login')

        _logger.warning(
            "acting_employee_login auth: authenticate called login=%r "
            "is_second_step=%s interactive=%s params_keys=%s",
            login,
            is_second_step,
            (user_agent_env or {}).get('interactive'),
            sorted(request.params.keys()) if request and getattr(request, 'params', None) else [],
        )

        if is_second_step:
            second_step_identity = self._authenticate_second_step_from_request(login)

        auth_info = super().authenticate(credential, user_agent_env)

        if second_step_identity:
            if second_step_identity._name == 'acting.branch.access':
                self._store_branch_access_session(second_step_identity)
            else:
                self._store_acting_employee_session(second_step_identity)
        elif is_second_step:
            _logger.warning(
                "acting_employee_login auth: second step requested but no identity stored "
                "login=%r",
                login,
            )

        from ..acting_log import _session_snapshot
        _logger.warning(
            "acting_employee_login auth: authenticate done uid=%s session=%s",
            auth_info.get('uid'),
            _session_snapshot(),
        )
        return auth_info
