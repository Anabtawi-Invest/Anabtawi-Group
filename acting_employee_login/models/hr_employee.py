# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)


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
            # Same pattern as res.users._set_new_password: the web client
            # submits False/'' for empty fields, and this field always
            # displays empty after save. Never clear the hash on empty.
            if not password:
                continue
            employee._set_acting_login_password(password)

    def _set_acting_login_password(self, password):
        self.ensure_one()
        if not password:
            return
        hashed = self.env['res.users']._crypt_context().hash(password)
        self.sudo().write({'acting_login_password_hash': hashed})
        _logger.warning(
            "acting_employee_login: set acting password hash for employee_id=%s name=%r",
            self.id,
            self.name,
        )

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
            _logger.warning(
                "acting_employee_login: missing name or password "
                "name_empty=%s password_empty=%s",
                not bool(name),
                not bool(password),
            )
            raise AccessDenied(
                self.env._('Employee name and employee password are required.')
            )

        employees = self.sudo().search([('name', '=ilike', name)])
        with_hash = employees.filtered(lambda emp: bool(emp.acting_login_password_hash))
        matches = employees.filtered(
            lambda emp: emp._check_acting_login_password(password)
        )
        _logger.warning(
            "acting_employee_login: name lookup name=%r found=%s with_hash=%s "
            "matches=%s ids=%s",
            name,
            len(employees),
            len(with_hash),
            len(matches),
            employees.ids,
        )
        if len(matches) != 1:
            raise AccessDenied(
                self.env._('Wrong employee name or employee password.')
            )
        return matches
