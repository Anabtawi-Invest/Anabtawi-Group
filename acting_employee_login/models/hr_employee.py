# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessDenied


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    acting_login_password = fields.Char(
        string='Acting Login Password',
        compute='_compute_acting_login_password',
        inverse='_inverse_acting_login_password',
        store=False,
        copy=False,
        groups='hr.group_hr_user',
        help='Password used together with the employee name on the login page '
             'to identify who is acting after a shared user signs in.',
    )
    acting_login_password_hash = fields.Char(
        string='Acting Login Password Hash',
        copy=False,
        groups='base.group_system',
    )

    def _compute_acting_login_password(self):
        for employee in self:
            employee.acting_login_password = ''

    def _inverse_acting_login_password(self):
        for employee in self:
            password = employee.acting_login_password or ''
            employee._set_acting_login_password(password)

    def _set_acting_login_password(self, password):
        self.ensure_one()
        if not password:
            self.sudo().write({'acting_login_password_hash': False})
            return
        hashed = self.env['res.users']._crypt_context().hash(password)
        self.sudo().write({'acting_login_password_hash': hashed})

    def _check_acting_login_password(self, password):
        self.ensure_one()
        if not password or not self.acting_login_password_hash:
            return False
        return self.env['res.users']._crypt_context().verify(
            password, self.acting_login_password_hash
        )

    @api.model
    def _authenticate_acting_employee(self, name, password):
        """Return the employee matching name + acting password, or raise."""
        name = (name or '').strip()
        password = password or ''
        if not name or not password:
            raise AccessDenied(
                self.env._('Employee name and employee password are required.')
            )

        employees = self.sudo().search([('name', '=ilike', name)])
        matches = employees.filtered(
            lambda emp: emp._check_acting_login_password(password)
        )
        if len(matches) != 1:
            raise AccessDenied(
                self.env._('Wrong employee name or employee password.')
            )
        return matches
