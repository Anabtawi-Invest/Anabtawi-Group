# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    acting_login_password = fields.Char(
        string='Acting Login Password',
        store=False,
        copy=False,
        groups='hr.group_hr_user',
        help='Password used together with the employee name on the login page '
             'to identify who is acting after a shared user signs in. '
             'Leave empty to keep the current password.',
    )
    acting_login_password_hash = fields.Char(
        string='Acting Login Password Hash',
        copy=False,
        groups='base.group_system',
    )
    acting_login_password_set = fields.Boolean(
        string='Acting Password Set',
        compute='_compute_acting_login_password_set',
        groups='hr.group_hr_user',
    )

    @api.depends('acting_login_password_hash')
    def _compute_acting_login_password_set(self):
        for employee in self:
            employee.acting_login_password_set = bool(
                employee.sudo().acting_login_password_hash
            )

    @api.model_create_multi
    def create(self, vals_list):
        passwords = [vals.pop('acting_login_password', None) for vals in vals_list]
        employees = super().create(vals_list)
        for employee, password in zip(employees, passwords):
            if password:
                employee._set_acting_login_password(password)
        return employees

    def write(self, vals):
        password = vals.pop('acting_login_password', None)
        res = super().write(vals)
        # Web client submits False/'' for empty password fields; ignore those
        # so a later save does not wipe a previously stored hash.
        if password:
            for employee in self:
                employee._set_acting_login_password(password)
        return res

    def _set_acting_login_password(self, password):
        self.ensure_one()
        if not password:
            return
        hashed = self.env['res.users']._crypt_context().hash(password)
        # Direct SQL avoids nested-write / field-group issues while hashing.
        self.env.cr.execute(
            'UPDATE hr_employee SET acting_login_password_hash = %s WHERE id = %s',
            (hashed, self.id),
        )
        self.invalidate_recordset(['acting_login_password_hash', 'acting_login_password_set'])
        _logger.warning(
            "acting_employee_login: set acting password hash for employee_id=%s name=%r",
            self.id,
            self.name,
        )

    def _get_acting_login_password_hash(self):
        self.ensure_one()
        self.env.cr.execute(
            'SELECT acting_login_password_hash FROM hr_employee WHERE id = %s',
            (self.id,),
        )
        row = self.env.cr.fetchone()
        return row[0] if row else False

    def _check_acting_login_password(self, password):
        self.ensure_one()
        password_hash = self._get_acting_login_password_hash()
        if not password or not password_hash:
            return False
        return self.env['res.users']._crypt_context().verify(password, password_hash)

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
        with_hash = employees.filtered(lambda emp: bool(emp._get_acting_login_password_hash()))
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
