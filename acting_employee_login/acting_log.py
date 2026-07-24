# -*- coding: utf-8 -*-

import logging

from odoo.http import request

_logger = logging.getLogger(__name__)


def _session_snapshot():
    if not request or not getattr(request, 'session', None):
        return {'has_request': False}
    session = request.session
    return {
        'has_request': True,
        'uid': session.uid,
        'sid_prefix': (session.sid or '')[:12],
        'acting_branch_access_id': session.get('acting_branch_access_id'),
        'acting_branch_name': session.get('acting_branch_name'),
        'acting_employee_id': session.get('acting_employee_id'),
        'acting_employee_name': session.get('acting_employee_name'),
    }


def _context_snapshot(env):
    ctx = env.context if env else {}
    return {
        'acting_branch_access_id': ctx.get('acting_branch_access_id'),
        'acting_branch_name': ctx.get('acting_branch_name'),
        'acting_employee_id': ctx.get('acting_employee_id'),
        'acting_employee_name': ctx.get('acting_employee_name'),
    }


def log_chatter_debug(event, **details):
    _logger.warning(
        "acting_employee_login chatter_debug [%s] %s",
        event,
        details,
    )
