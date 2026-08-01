# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    acting_login_password = fields.Char(
        string='Acting Login Password',
        compute='_compute_acting_login_password',
        inverse='_inverse_acting_login_password',
        store=False,
        copy=False,
        groups='hr.group_hr_user',
        help='Password used together with the employee number on the login page. '
             'The employee must also be linked to the user account they sign in with.',
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

    @api.constrains('user_id')
    def _check_acting_login_user_unique(self):
        for employee in self.filtered('user_id'):
            duplicate = self.search([
                ('user_id', '=', employee.user_id.id),
                ('id', '!=', employee.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(self.env._(
                    'User "%(user)s" is already linked to employee "%(employee)s". '
                    'Each user can only be linked to one employee.',
                    user=employee.user_id.display_name,
                    employee=duplicate.display_name,
                ))

    @api.model
    def _authenticate_acting_employee(self, employee_number, password, user=None):
        """Return the employee matching number + password + linked user, or raise."""
        employee_number = (employee_number or '').strip()
        password = password or ''
        if not employee_number or not password:
            raise AccessDenied(
                self.env._('Employee number and employee password are required.')
            )

        employees = self.sudo().search([('employee_number', '=', employee_number)])
        if len(employees) != 1:
            raise AccessDenied(
                self.env._('Wrong employee number or employee password.')
            )

        employee = employees
        if not employee._check_acting_login_password(password):
            raise AccessDenied(
                self.env._('Wrong employee number or employee password.')
            )

        if not user or not employee.user_id or employee.user_id.id != user.id:
            raise AccessDenied(
                self.env._('This employee is not linked to this user.')
            )

        return employee
