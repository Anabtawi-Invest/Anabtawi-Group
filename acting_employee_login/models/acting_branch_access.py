# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, ValidationError

_logger = logging.getLogger(__name__)


class ActingBranchAccess(models.Model):
    _name = 'acting.branch.access'
    _description = 'Branch Login Access'
    _order = 'user_id, branch_name'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        ondelete='cascade',
        index=True,
    )
    branch_name = fields.Char(required=True, index=True)
    branch_password = fields.Char(
        string='Password',
        compute='_compute_branch_password',
        inverse='_inverse_branch_password',
        store=False,
        copy=False,
    )
    branch_password_hash = fields.Char(copy=False, groups='base.group_system')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            'acting_branch_access_user_branch_uniq',
            'unique(user_id, branch_name)',
            'Each user can have only one password per branch name.',
        ),
    ]

    @api.constrains('branch_name')
    def _check_branch_name(self):
        for record in self:
            if not (record.branch_name or '').strip():
                raise ValidationError(self.env._('Branch name is required.'))

    def _compute_branch_password(self):
        for record in self:
            record.branch_password = ''

    def _inverse_branch_password(self):
        for record in self:
            record._set_branch_password(record.branch_password or '')

    def _set_branch_password(self, password):
        self.ensure_one()
        if not password:
            self.write({'branch_password_hash': False})
            return
        hashed = self.env['res.users']._crypt_context().hash(password)
        self.write({'branch_password_hash': hashed})

    def _check_branch_password(self, password):
        self.ensure_one()
        if not password or not self.branch_password_hash:
            return False
        return self.env['res.users']._crypt_context().verify(
            password, self.branch_password_hash
        )

    @api.model
    def _authenticate_branch_access(self, user, branch_name, password):
        """Return the branch access row for user + branch + password."""
        branch_name = (branch_name or '').strip()
        password = password or ''
        if not branch_name or not password:
            _logger.warning(
                "acting_employee_login: missing branch name or password user_id=%s",
                user.id,
            )
            raise AccessDenied(
                self.env._('Branch name and password are required.')
            )

        access = self.sudo().search([
            ('user_id', '=', user.id),
            ('branch_name', '=ilike', branch_name),
            ('active', '=', True),
        ], limit=1)
        if not access or not access._check_branch_password(password):
            _logger.warning(
                "acting_employee_login: branch auth failed user_id=%s branch_name=%r found=%s",
                user.id,
                branch_name,
                bool(access),
            )
            raise AccessDenied(
                self.env._('Wrong branch name or password.')
            )
        return access
