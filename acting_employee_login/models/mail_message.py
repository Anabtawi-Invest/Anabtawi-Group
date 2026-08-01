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
    def _get_acting_employee_vals(self, model_name):
        if not self._is_acting_employee_enabled_for_model(model_name):
            return {}

        acting_id = self.env.context.get('acting_employee_id')
        acting_name = self.env.context.get('acting_employee_name')
        if not acting_id and request and getattr(request, 'session', None):
            acting_id = request.session.get('acting_employee_id')
            acting_name = request.session.get('acting_employee_name')

        if not acting_id:
            return {}

        employee = self.env['hr.employee'].sudo().browse(acting_id).exists()
        if not employee:
            return {}

        return {
            'acting_employee_id': employee.id,
            'acting_employee_name': acting_name or employee.name,
        }

    @api.model
    def _get_acting_branch_vals(self, model_name):
        if not self._is_acting_employee_enabled_for_model(model_name):
            return {}

        branch_access_id = self.env.context.get('acting_branch_access_id')
        branch_name = self.env.context.get('acting_branch_name')
        if not branch_access_id and request and getattr(request, 'session', None):
            branch_access_id = request.session.get('acting_branch_access_id')
            branch_name = request.session.get('acting_branch_name')

        if not branch_access_id and not branch_name:
            return {}

        vals = {}
        if branch_access_id:
            access = self.env['acting.branch.access'].sudo().browse(
                branch_access_id
            ).exists()
            if access:
                vals['acting_branch_access_id'] = access.id
                vals['acting_branch_name'] = branch_name or access.branch_name
        elif branch_name:
            vals['acting_branch_name'] = branch_name
        return vals

    @api.model
    def _get_acting_identity_vals(self, model_name):
        """Return acting employee or branch values for enabled models."""
        if not self._is_acting_employee_enabled_for_model(model_name):
            return {}

        branch_vals = self._get_acting_branch_vals(model_name)
        if branch_vals:
            return branch_vals
        return self._get_acting_employee_vals(model_name)

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
