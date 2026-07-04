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
        help="5-digit Employee Portal OTP. Valid for 5 minutes after generation.",
        readonly=False,
    )
    employee_password_generated_at = fields.Datetime(
        string="Employee OTP Generated At",
        copy=False,
        readonly=True,
    )
    employee_password_expires_at = fields.Datetime(
        string="Employee OTP Expires At",
        copy=False,
        readonly=True,
    )

    @api.model
    def _generate_employee_password(self, length=5):
        digits = string.digits
        return "".join(secrets.choice(digits) for _ in range(int(length)))

    def action_generate_employee_portal_otp(self):
        """Generate a 5-digit OTP for the Employee Portal.

        The OTP is saved on employee_password for compatibility with the existing
        employee_request module and expires after 5 minutes.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        expires_at = now + relativedelta(minutes=5)
        otp = self._generate_employee_password(length=5)
        self.sudo().write({
            "employee_password": otp,
            "employee_password_generated_at": now,
            "employee_password_expires_at": expires_at,
        })
        return {
            "success": True,
            "employee_otp": otp,
            "otp_number": otp,
            "otp_generated_at": fields.Datetime.to_string(now),
            "otp_expires_at": fields.Datetime.to_string(expires_at),
            "expires_in_seconds": 300,
        }

    @api.model
    def _cron_clear_expired_employee_passwords(self):
        now = fields.Datetime.now()
        employees = self.sudo().search([
            ("employee_password", "!=", False),
            ("employee_password_expires_at", "!=", False),
            ("employee_password_expires_at", "<=", now),
        ])
        employees.write({"employee_password": False})

    @api.model
    def _cron_rotate_employee_password(self, force=False):
        """Rotate employee passwords (scheduled), or initialize missing / stale ones.

        By default, only employees with no timestamp or a password older than 24 hours
        are updated — so a manual "Run" shortly after the last generation does nothing.

        Pass ``force=True`` (e.g. from the server action "Force rotate employee passwords")
        to regenerate for all employees.
        """
        now = fields.Datetime.now()

        if force:
            domain = []
        else:
            cutoff = now - relativedelta(hours=24)
            domain = [
                "|",
                ("employee_password_generated_at", "=", False),
                ("employee_password_generated_at", "<", cutoff),
            ]

        employees = self.sudo().search(domain)
        for employee in employees:
            employee.write(
                {
                    "employee_password": self._generate_employee_password(),
                    "employee_password_generated_at": now,
                    "employee_password_expires_at": now + relativedelta(minutes=5),
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

        now = fields.Datetime.now()
        if employee.employee_password_expires_at:
            return employee.employee_password_expires_at > now

        # Backward compatibility for records generated before the expires field existed.
        cutoff = now - relativedelta(minutes=5)
        return employee.employee_password_generated_at >= cutoff

