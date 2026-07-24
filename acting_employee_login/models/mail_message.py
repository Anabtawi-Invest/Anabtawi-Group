# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.http import request


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
        return {name.strip() for name in param.split(',') if name.strip()}

    @api.model
    def _is_acting_employee_enabled_for_model(self, model_name):
        if not model_name:
            return False
        enabled = self._get_acting_employee_enabled_modules()
        if not enabled:
            return False
        model = self.env['ir.model']._get(model_name)
        if not model:
            return False
        model_modules = {
            name.strip()
            for name in (model.modules or '').split(',')
            if name.strip()
        }
        return bool(enabled & model_modules)

    @api.model
    def _get_session_acting_identity(self):
        if not request or not getattr(request, 'session', None):
            return {}
        session = request.session
        if session.get('acting_branch_access_id'):
            return {
                'acting_branch_access_id': session['acting_branch_access_id'],
                'acting_branch_name': session.get('acting_branch_name') or '',
            }
        if session.get('acting_employee_id'):
            return {
                'acting_employee_id': session['acting_employee_id'],
                'acting_employee_name': session.get('acting_employee_name') or '',
            }
        return {}

    @api.model
    def _get_acting_identity_vals(self, model_name):
        if not self._is_acting_employee_enabled_for_model(model_name):
            return {}

        acting_employee_id = self.env.context.get('acting_employee_id')
        acting_employee_name = self.env.context.get('acting_employee_name')
        acting_branch_access_id = self.env.context.get('acting_branch_access_id')
        acting_branch_name = self.env.context.get('acting_branch_name')

        session_vals = self._get_session_acting_identity()
        acting_branch_access_id = acting_branch_access_id or session_vals.get(
            'acting_branch_access_id'
        )
        acting_branch_name = acting_branch_name or session_vals.get('acting_branch_name')
        acting_employee_id = acting_employee_id or session_vals.get('acting_employee_id')
        acting_employee_name = acting_employee_name or session_vals.get(
            'acting_employee_name'
        )

        if acting_branch_access_id:
            access = self.env['acting.branch.access'].sudo().browse(
                acting_branch_access_id
            ).exists()
            if access:
                return {
                    'acting_branch_access_id': access.id,
                    'acting_branch_name': acting_branch_name or access.branch_name,
                }
            return {}

        if not acting_employee_id:
            return {}

        employee = self.env['hr.employee'].sudo().browse(acting_employee_id).exists()
        if not employee:
            return {}

        return {
            'acting_employee_id': employee.id,
            'acting_employee_name': acting_employee_name or employee.name,
        }

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
            acting_vals = self._get_acting_identity_vals(vals.get('model'))
            if acting_vals:
                vals.update(acting_vals)
        return super().create(vals_list)

    def _to_store_defaults(self, target: Store.Target):
        return super()._to_store_defaults(target) + [
            'acting_employee_name',
            'acting_branch_name',
        ]
