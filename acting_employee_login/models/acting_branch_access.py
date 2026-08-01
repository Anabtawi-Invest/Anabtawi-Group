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
        copy=False,
        help='Branch password used at the second login step.',
    )
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

    def _check_branch_password(self, password):
        self.ensure_one()
        if not password or not self.branch_password:
            return False
        return str(self.branch_password).strip() == str(password).strip()

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
