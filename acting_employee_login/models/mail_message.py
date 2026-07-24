# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.http import request

from ..acting_log import (
    _context_snapshot,
    _session_snapshot,
    log_chatter_debug,
)

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = 'mail.message'

    acting_employee_id = fields.Many2one(
        'hr.employee',
        string='Acting Employee',
        index=True,
        ondelete='set null',
        copy=False,
    )
    acting_employee_name = fields.Char(
        string='Acting Employee Name',
        copy=False,
    )
    acting_branch_access_id = fields.Many2one(
        'acting.branch.access',
        string='Acting Branch Access',
        index=True,
        ondelete='set null',
        copy=False,
    )
    acting_branch_name = fields.Char(
        string='Acting Branch Name',
        copy=False,
    )

    @api.model
    def _get_acting_employee_enabled_modules(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'acting_employee_login.enabled_modules', ''
        )
        enabled = {name.strip() for name in param.split(',') if name.strip()}
        if not enabled:
            return {'stock', 'hr'}
        return enabled

    @api.model
    def _is_acting_employee_enabled_for_model(self, model_name):
        if not model_name:
            return False, 'missing_model_name'
        enabled = self._get_acting_employee_enabled_modules()
        if not enabled:
            return False, 'no_enabled_modules'
        model = self.env['ir.model']._get(model_name)
        if not model:
            return False, 'model_not_found'
        model_modules = {
            name.strip()
            for name in (model.modules or '').split(',')
            if name.strip()
        }
        if not (enabled & model_modules):
            return False, {
                'reason': 'module_not_enabled',
                'enabled_modules': sorted(enabled),
                'model_modules': sorted(model_modules),
            }
        return True, 'ok'

    @api.model
    def _get_session_acting_identity(self):
        if not request or not getattr(request, 'session', None):
            return {}, 'no_http_request'
        session = request.session
        if session.get('acting_branch_access_id'):
            return {
                'acting_branch_access_id': session['acting_branch_access_id'],
                'acting_branch_name': session.get('acting_branch_name') or '',
            }, 'session_branch'
        if session.get('acting_employee_id'):
            return {
                'acting_employee_id': session['acting_employee_id'],
                'acting_employee_name': session.get('acting_employee_name') or '',
            }, 'session_employee'
        return {}, 'session_empty'

    @api.model
    def _get_acting_identity_vals(self, model_name):
        enabled, enabled_reason = self._is_acting_employee_enabled_for_model(model_name)
        if not enabled:
            log_chatter_debug(
                'identity_skipped_module',
                model=model_name,
                reason=enabled_reason,
                session=_session_snapshot(),
                context=_context_snapshot(self.env),
            )
            return {}

        acting_employee_id = self.env.context.get('acting_employee_id')
        acting_employee_name = self.env.context.get('acting_employee_name')
        acting_branch_access_id = self.env.context.get('acting_branch_access_id')
        acting_branch_name = self.env.context.get('acting_branch_name')

        session_vals, session_source = self._get_session_acting_identity()
        acting_branch_access_id = acting_branch_access_id or session_vals.get(
            'acting_branch_access_id'
        )
        acting_branch_name = acting_branch_name or session_vals.get('acting_branch_name')
        acting_employee_id = acting_employee_id or session_vals.get('acting_employee_id')
        acting_employee_name = acting_employee_name or session_vals.get(
            'acting_employee_name'
        )

        user = self.env.user
        if user and user._is_public() is False:
            branch_user = bool(getattr(user, 'is_branch_user', False))
        else:
            branch_user = None

        if acting_branch_access_id:
            access = self.env['acting.branch.access'].sudo().browse(
                acting_branch_access_id
            ).exists()
            if access:
                result = {
                    'acting_branch_access_id': access.id,
                    'acting_branch_name': acting_branch_name or access.branch_name,
                }
                log_chatter_debug(
                    'identity_applied_branch',
                    model=model_name,
                    session_source=session_source,
                    result=result,
                    session=_session_snapshot(),
                    context=_context_snapshot(self.env),
                    user_id=user.id if user else None,
                    is_branch_user=branch_user,
                )
                return result
            log_chatter_debug(
                'identity_branch_access_missing',
                model=model_name,
                acting_branch_access_id=acting_branch_access_id,
                session=_session_snapshot(),
                context=_context_snapshot(self.env),
            )
            return {}

        if not acting_employee_id:
            log_chatter_debug(
                'identity_no_session_identity',
                model=model_name,
                session_source=session_source,
                session=_session_snapshot(),
                context=_context_snapshot(self.env),
                user_id=user.id if user else None,
                is_branch_user=branch_user,
                login=user.login if user and not user._is_public() else None,
            )
            return {}

        employee = self.env['hr.employee'].sudo().browse(acting_employee_id).exists()
        if not employee:
            log_chatter_debug(
                'identity_employee_missing',
                model=model_name,
                acting_employee_id=acting_employee_id,
                session=_session_snapshot(),
            )
            return {}

        result = {
            'acting_employee_id': employee.id,
            'acting_employee_name': acting_employee_name or employee.name,
        }
        log_chatter_debug(
            'identity_applied_employee',
            model=model_name,
            session_source=session_source,
            result=result,
            session=_session_snapshot(),
        )
        return result

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (
                vals.get('acting_employee_id')
                or vals.get('acting_employee_name')
                or vals.get('acting_branch_access_id')
                or vals.get('acting_branch_name')
            ):
                continue
            model_name = vals.get('model')
            acting_vals = self._get_acting_identity_vals(model_name)
            if acting_vals:
                vals.update(acting_vals)
            elif model_name in ('stock.picking', 'stock.move', 'stock.move.line'):
                log_chatter_debug(
                    'message_create_no_identity',
                    model=model_name,
                    res_id=vals.get('res_id'),
                    message_type=vals.get('message_type'),
                    subtype_id=vals.get('subtype_id'),
                    session=_session_snapshot(),
                    context=_context_snapshot(self.env),
                )
        return super().create(vals_list)

    def _to_store_defaults(self, target: Store.Target):
        return super()._to_store_defaults(target) + [
            'acting_employee_name',
            'acting_branch_name',
        ]
