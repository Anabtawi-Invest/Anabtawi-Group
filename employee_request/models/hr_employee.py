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

    def _employee_password_db_snapshot(self):
        """Read OTP columns directly from DB for logging."""
        self.ensure_one()
        self.env.cr.execute(
            """
            SELECT employee_password,
                   employee_password_generated_at,
                   employee_password_expires_at,
                   company_id
              FROM hr_employee
             WHERE id = %s
            """,
            (self.id,),
        )
        row = self.env.cr.fetchone() or (None, None, None, None)
        return {
            "employee_id": self.id,
            "employee_name": self.name,
            "db_password": row[0] or False,
            "db_password_repr": repr(row[0]),
            "db_password_len": len(str(row[0] or "")),
            "db_generated_at": str(row[1]) if row[1] else None,
            "db_expires_at": str(row[2]) if row[2] else None,
            "db_company_id": row[3],
            "orm_password": self.employee_password or False,
            "orm_password_repr": repr(self.employee_password),
            "orm_generated_at": str(self.employee_password_generated_at)
            if self.employee_password_generated_at
            else None,
            "orm_expires_at": str(self.employee_password_expires_at)
            if self.employee_password_expires_at
            else None,
            "company_id": self.company_id.id,
            "company_name": self.company_id.display_name,
        }

    def write(self, vals):
        vals = dict(vals or {})
        password_in_vals = "employee_password" in vals
        before = {
            employee.id: employee._employee_password_db_snapshot()
            for employee in self
        }

        if password_in_vals:
            password = vals.get("employee_password")
            _logger.warning(
                "[employee_request] WRITE employee_password START ids=%s "
                "incoming_password_repr=%s incoming_len=%s incoming_keys=%s",
                self.ids,
                repr(password),
                len(str(password or "")),
                sorted(vals.keys()),
            )
            if password in (False, None, ""):
                vals["employee_password"] = False
                vals["employee_password_generated_at"] = False
                vals["employee_password_expires_at"] = False
            else:
                # Manual or portal OTP set: always refresh the 5-minute validity window.
                now = fields.Datetime.now()
                vals["employee_password"] = str(password).strip()
                vals["employee_password_generated_at"] = now
                vals["employee_password_expires_at"] = now + relativedelta(minutes=5)
                _logger.warning(
                    "[employee_request] WRITE employee_password NORMALIZED ids=%s "
                    "stored_repr=%s generated_at=%s expires_at=%s",
                    self.ids,
                    repr(vals["employee_password"]),
                    vals["employee_password_generated_at"],
                    vals["employee_password_expires_at"],
                )
        elif any(
            key in vals
            for key in (
                "employee_password_generated_at",
                "employee_password_expires_at",
            )
        ):
            _logger.warning(
                "[employee_request] WRITE OTP timestamps without password ids=%s vals=%s",
                self.ids,
                {k: vals.get(k) for k in vals},
            )

        res = super().write(vals)

        if password_in_vals:
            self.invalidate_recordset(
                [
                    "employee_password",
                    "employee_password_generated_at",
                    "employee_password_expires_at",
                ]
            )
            for employee in self:
                after = employee._employee_password_db_snapshot()
                _logger.warning(
                    "[employee_request] WRITE employee_password DONE id=%s "
                    "before=%s after=%s",
                    employee.id,
                    before.get(employee.id),
                    after,
                )
        return res

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
                _logger.warning(
                    "[employee_request] CREATE employee_password password_repr=%s expires_at=%s",
                    repr(vals["employee_password"]),
                    vals["employee_password_expires_at"],
                )
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
        if employees:
            _logger.info(
                "[employee_request] clearing %s expired OTP(s): %s",
                len(employees),
                employees.mapped(lambda e: (e.id, e.name)),
            )
            employees.write({
                "employee_password": False,
                "employee_password_generated_at": False,
                "employee_password_expires_at": False,
            })

    def action_generate_employee_portal_otp_button(self):
        """UI button: generate a fresh OTP and show it to the HR manager."""
        self.ensure_one()
        result = self.action_generate_employee_portal_otp()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Employee OTP Generated",
                "message": (
                    f"OTP: {result.get('otp_number')} "
                    f"(valid until {result.get('otp_expires_at')} UTC)"
                ),
                "type": "success",
                "sticky": True,
            },
        }

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

        # Bypass cache / confirm real DB value (rules out stale ORM cache / company tricks).
        self.env.cr.execute(
            """
            SELECT employee_password,
                   employee_password_generated_at,
                   employee_password_expires_at,
                   company_id
              FROM hr_employee
             WHERE id = %s
            """,
            (employee.id,),
        )
        row = self.env.cr.fetchone()
        db_password = row[0] if row else None
        db_generated = row[1] if row else None
        db_expires = row[2] if row else None
        db_company_id = row[3] if row else None

        orm_password = employee.employee_password
        diag.update(
            {
                "employee_id": employee.id,
                "employee_name": employee.name,
                "employee_company_id": employee.company_id.id,
                "employee_company_name": employee.company_id.display_name,
                "db_company_id": db_company_id,
                "env_company_id": self.env.company.id if self.env.company else None,
                "has_stored_password": bool(orm_password),
                "stored_len": len(str(orm_password or "")),
                "db_has_password": bool(db_password),
                "db_stored_len": len(str(db_password or "")),
                "orm_equals_db": str(orm_password or "") == str(db_password or ""),
                "generated_at": fields.Datetime.to_string(employee.employee_password_generated_at)
                if employee.employee_password_generated_at
                else None,
                "expires_at": fields.Datetime.to_string(employee.employee_password_expires_at)
                if employee.employee_password_expires_at
                else None,
                "db_generated_at": fields.Datetime.to_string(db_generated) if db_generated else None,
                "db_expires_at": fields.Datetime.to_string(db_expires) if db_expires else None,
            }
        )

        password = str(password).strip()
        if not password.isdigit():
            diag["reason"] = "not_numeric"
            return diag

        stored = str(db_password or orm_password or "").strip()
        if not stored:
            diag["reason"] = "no_stored_password"
            return diag

        if stored != password:
            diag["reason"] = "mismatch"
            return diag

        generated_at = employee.employee_password_generated_at or db_generated
        expires_at = employee.employee_password_expires_at or db_expires

        if not generated_at:
            diag["reason"] = "missing_generated_at"
            return diag

        if expires_at:
            if expires_at <= now:
                diag["reason"] = "expired"
                diag["expired_seconds_ago"] = int((now - expires_at).total_seconds())
                return diag
            diag["ok"] = True
            diag["reason"] = "ok"
            return diag

        cutoff = now - relativedelta(minutes=5)
        if generated_at < cutoff:
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
