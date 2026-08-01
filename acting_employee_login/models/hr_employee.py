# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessDenied


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    acting_login_user_id = fields.Many2one(
        'res.users',
        string='Acting Login User',
        help='Odoo user this employee may sign in with at the second login step. '
             'Multiple employees can share the same acting login user.',
        groups='hr.group_hr_user',
    )
    acting_login_password = fields.Char(
        string='Acting Login Password',
        compute='_compute_acting_login_password',
        inverse='_inverse_acting_login_password',
        store=False,
        copy=False,
        groups='hr.group_hr_user',
        help='Password used together with the employee number on the login page. '
             'The employee must also be linked to the acting login user they sign in with.',
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

        if (
            not user
            or not employee.acting_login_user_id
            or employee.acting_login_user_id.id != user.id
        ):
            raise AccessDenied(
                self.env._('This employee is not linked to this user.')
            )

        return employee
