# -*- coding: utf-8 -*-

import secrets
import string

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    employee_password = fields.Char(
        string="Employee Password",
        copy=False,
        help="Auto-generated password, rotated every 24 hours by a scheduled action.",
        readonly=True,
    )
    employee_password_generated_at = fields.Datetime(
        string="Employee Password Generated At",
        copy=False,
        readonly=True,
    )

    @api.model
    def _generate_employee_password(self, length=12):
        digits = string.digits
        return "".join(secrets.choice(digits) for _ in range(int(length)))

    @api.model
    def _cron_rotate_employee_password(self):
        """Rotate employee passwords every 24 hours (or initialize missing ones)."""
        now = fields.Datetime.now()
        cutoff = now - relativedelta(hours=24)

        employees = self.sudo().search(
            [
                "|",
                ("employee_password_generated_at", "=", False),
                ("employee_password_generated_at", "<", cutoff),
            ]
        )
        for employee in employees:
            employee.write(
                {
                    "employee_password": self._generate_employee_password(),
                    "employee_password_generated_at": now,
                }
            )

    # -----------------------
    # POS helpers (RPC calls)
    # -----------------------
    @api.model
    def pos_employee_request_get_employees(self, config_id=False, search=False, limit=50):
        """Return employees for POS popup selection.

        We keep it minimal: name + barcode, and sudo because POS users might not have HR access.
        """
        domain = [("active", "=", True)]
        if config_id:
            config = self.env["pos.config"].sudo().browse(int(config_id)).exists()
            if config and config.company_id:
                domain += ["|", ("company_id", "=", False), ("company_id", "=", config.company_id.id)]

        if search:
            search = str(search)
            domain += ["|", ("name", "ilike", search), ("barcode", "ilike", search)]

        employees = self.sudo().search(domain, limit=int(limit), order="name")
        return [
            {"id": e.id, "name": e.name, "barcode": e.barcode or ""}
            for e in employees
        ]

    @api.model
    def pos_employee_request_check_password(self, employee_id, password):
        """Validate that the given password matches the employee's current password.

        Also enforces the 24h validity window.
        """
        if not employee_id or password in (False, None, ""):
            return False

        employee = self.sudo().browse(int(employee_id)).exists()
        if not employee:
            return False

        # enforce numeric password
        password = str(password).strip()
        if not password.isdigit():
            return False

        if not employee.employee_password or str(employee.employee_password) != password:
            return False

        if not employee.employee_password_generated_at:
            return False

        cutoff = fields.Datetime.now() - relativedelta(hours=24)
        return employee.employee_password_generated_at >= cutoff

