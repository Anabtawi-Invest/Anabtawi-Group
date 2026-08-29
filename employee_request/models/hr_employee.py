# -*- coding: utf-8 -*-

import logging
import secrets
import string

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


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

    def write(self, vals):
        vals = dict(vals or {})
        if "employee_password" in vals:
            password = vals.get("employee_password")
            if password in (False, None, ""):
                vals.setdefault("employee_password_generated_at", False)
                vals.setdefault("employee_password_expires_at", False)
            else:
                # Manual or portal OTP set: always refresh the 5-minute validity window.
                now = fields.Datetime.now()
                vals["employee_password"] = str(password).strip()
                vals["employee_password_generated_at"] = now
                vals["employee_password_expires_at"] = now + relativedelta(minutes=5)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        prepared = []
        for vals in vals_list:
            vals = dict(vals or {})
            password = vals.get("employee_password")
            if password not in (False, None, ""):
                vals["employee_password"] = str(password).strip()
                vals["employee_password_generated_at"] = now
                vals["employee_password_expires_at"] = now + relativedelta(minutes=5)
            prepared.append(vals)
        return super().create(prepared)

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
    def pos_employee_request_password_diag(self, employee_id, password):
        """Return why an OTP check would pass/fail (for logs / debugging)."""
        now = fields.Datetime.now()
        diag = {
            "ok": False,
            "reason": "unknown",
            "employee_id": employee_id or None,
            "now": fields.Datetime.to_string(now),
            "submitted_len": len(str(password or "").strip()),
            "submitted_isdigit": str(password or "").strip().isdigit(),
        }

        if not employee_id or password in (False, None, ""):
            diag["reason"] = "missing_employee_or_password"
            return diag

        employee = self.sudo().browse(int(employee_id)).exists()
        if not employee:
            diag["reason"] = "employee_not_found"
            return diag

        diag.update(
            {
                "employee_id": employee.id,
                "employee_name": employee.name,
                "has_stored_password": bool(employee.employee_password),
                "stored_len": len(str(employee.employee_password or "")),
                "generated_at": fields.Datetime.to_string(employee.employee_password_generated_at)
                if employee.employee_password_generated_at
                else None,
                "expires_at": fields.Datetime.to_string(employee.employee_password_expires_at)
                if employee.employee_password_expires_at
                else None,
            }
        )

        password = str(password).strip()
        if not password.isdigit():
            diag["reason"] = "not_numeric"
            return diag

        stored = str(employee.employee_password or "").strip()
        if not stored:
            diag["reason"] = "no_stored_password"
            return diag

        if stored != password:
            diag["reason"] = "mismatch"
            return diag

        if not employee.employee_password_generated_at:
            diag["reason"] = "missing_generated_at"
            return diag

        if employee.employee_password_expires_at:
            if employee.employee_password_expires_at <= now:
                diag["reason"] = "expired"
                diag["expired_seconds_ago"] = int(
                    (now - employee.employee_password_expires_at).total_seconds()
                )
                return diag
            diag["ok"] = True
            diag["reason"] = "ok"
            return diag

        cutoff = now - relativedelta(minutes=5)
        if employee.employee_password_generated_at < cutoff:
            diag["reason"] = "expired_fallback_5min"
            return diag

        diag["ok"] = True
        diag["reason"] = "ok"
        return diag

    @api.model
    def pos_employee_request_check_password(self, employee_id, password):
        """Validate that the given password matches the employee's current password.

        Also enforces the OTP expiry window.
        """
        diag = self.pos_employee_request_password_diag(employee_id, password)
        if not diag.get("ok"):
            _logger.info(
                "[employee_request] OTP check failed employee_id=%s reason=%s diag=%s",
                employee_id,
                diag.get("reason"),
                {k: v for k, v in diag.items() if k not in ("ok",)},
            )
        return bool(diag.get("ok"))
