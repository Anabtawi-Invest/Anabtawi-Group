import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AnabtawiMobileDevice(models.Model):
    _name = "anabtawi.mobile.device"
    _description = "Employee App registered device"
    _rec_name = "display_name"

    user_id = fields.Many2one(
        "res.users", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Employee", compute="_compute_employee_id", store=True, index=True
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)
    device_uid = fields.Char(string="Device UID", index=True)
    device_name = fields.Char(string="Device Name")
    registered_ip = fields.Char(string="Registered IP", readonly=True)
    last_ip = fields.Char(string="Last IP", readonly=True)
    token_index = fields.Char(string="Token Index", size=8, index=True)
    token_hash = fields.Char(string="Token Hash", groups="base.group_system")
    active = fields.Boolean(default=True)
    registered_at = fields.Datetime(string="Registered At", readonly=True)
    last_login = fields.Datetime(string="Last Login", readonly=True)
    token_expires_at = fields.Datetime(
        string="Token Expires At",
        readonly=True,
        index=True,
    )

    _sql_constraints = [
        (
            "user_device_uid_unique",
            "unique(user_id, device_uid)",
            "The same Employee App device is already registered for this user.",
        ),
    ]

    @api.depends("user_id")
    def _compute_employee_id(self):
        Employee = self.env["hr.employee"].sudo()
        for rec in self:
            rec.employee_id = Employee.search([("user_id", "=", rec.user_id.id)], limit=1) if rec.user_id else False

    @api.depends("user_id", "device_name", "device_uid")
    def _compute_display_name(self):
        for rec in self:
            user_name = rec.user_id.name or rec.user_id.login or _("Unknown User")
            device = rec.device_name or rec.device_uid or _("Employee App Device")
            rec.display_name = "%s - %s" % (user_name, device)

    @api.model
    def _get_pepper(self):
        return self.env["ir.config_parameter"].sudo().get_param("anabtawi_mobile.token_pepper") or ""

    @api.model
    def _hash_plain_token(self, plain_token):
        if not plain_token:
            return ""
        pepper = self._get_pepper().encode()
        return hmac.new(pepper, plain_token.encode(), hashlib.sha256).hexdigest()

    @api.model
    def _issue_plain_token(self):
        return secrets.token_urlsafe(32)

    @api.model
    def _token_ttl_days(self):
        raw_value = self.env["ir.config_parameter"].sudo().get_param(
            "anabtawi_mobile.token_ttl_days", "30"
        )
        try:
            return max(1, min(int(raw_value), 365))
        except (TypeError, ValueError):
            return 30

    def _apply_new_tokens(self, plain_token, ip_address=None):
        digest = self._hash_plain_token(plain_token)
        vals = {
            "token_hash": digest,
            "token_index": digest[:8] if digest else False,
            "last_login": fields.Datetime.now(),
            "active": True,
            "token_expires_at": fields.Datetime.now() + timedelta(days=self._token_ttl_days()),
        }
        if ip_address:
            vals["last_ip"] = ip_address
        self.sudo().write(vals)

    @api.model
    def register_or_refresh_login(self, user, device_uid_clean, device_name=None, ip_address=None):
        """Register/refresh an Employee App login.

        This method is called only by /anabtawi/mobile/* Employee App API routes.
        It does not alter normal Odoo web login behavior, so internal Odoo users can
        still use Odoo from multiple browsers/devices.
        """
        if not device_uid_clean:
            raise UserError(_("device_uid is required."))
        self_sudo = self.sudo()

        active_devices = self_sudo.search([
            ("user_id", "=", user.id),
            ("active", "=", True),
        ])

        active_other_devices = active_devices.filtered(lambda d: d.device_uid != device_uid_clean)
        if active_other_devices:
            _logger.warning(
                "Employee App login rejected by single-device constraint: user_id=%s device_uid=%s active_device_uid=%s",
                user.id,
                device_uid_clean,
                active_other_devices[0].device_uid,
            )
            raise UserError(_(
                "This employee already has a registered Employee App device. "
                "Please contact HR to reset the registered device."
            ))

        active_same_device = active_devices.filtered(lambda d: d.device_uid == device_uid_clean)[:1]

        plain = self_sudo._issue_plain_token()
        if active_same_device:
            vals = {"device_name": device_name or active_same_device.device_name}
            if ip_address:
                vals["last_ip"] = ip_address
            active_same_device.write(vals)
            active_same_device._apply_new_tokens(plain, ip_address=ip_address)
            return {"access_token": plain}

        inactive_device = self_sudo.search([
            ("user_id", "=", user.id),
            ("device_uid", "=", device_uid_clean),
        ], limit=1)
        if inactive_device:
            vals = {
                "device_name": device_name or inactive_device.device_name,
                "active": True,
            }
            if not inactive_device.registered_at:
                vals["registered_at"] = fields.Datetime.now()
            if ip_address:
                vals["registered_ip"] = inactive_device.registered_ip or ip_address
                vals["last_ip"] = ip_address
            inactive_device.write(vals)
            inactive_device._apply_new_tokens(plain, ip_address=ip_address)
            return {"access_token": plain}

        digest = self_sudo._hash_plain_token(plain)
        self_sudo.create({
            "user_id": user.id,
            "device_uid": device_uid_clean,
            "device_name": device_name or "",
            "registered_ip": ip_address or False,
            "last_ip": ip_address or False,
            "token_hash": digest,
            "token_index": digest[:8] if digest else False,
            "active": True,
            "registered_at": fields.Datetime.now(),
            "last_login": fields.Datetime.now(),
            "token_expires_at": fields.Datetime.now() + timedelta(days=self._token_ttl_days()),
        })
        return {"access_token": plain}

    @api.model
    def _find_bearer_device(self, plain_token):
        digest = self.sudo()._hash_plain_token(plain_token)
        if not digest:
            return self.browse()
        candidates = self.sudo().search([
            ("token_index", "=", digest[:8]),
            ("active", "=", True),
        ])
        return candidates.filtered(
            lambda device: device.token_hash
            and hmac.compare_digest(device.token_hash, digest)
        )[:1]

    @api.model
    def authenticate_bearer_token(self, plain_token, ip_address=None):
        device = self._find_bearer_device(plain_token)
        if not device:
            return self.env["res.users"]
        if device.token_expires_at and device.token_expires_at <= fields.Datetime.now():
            device.action_revoke_token()
            return self.env["res.users"]
        if not device.user_id.active:
            device.action_revoke_token()
            return self.env["res.users"]
        vals = {"last_login": fields.Datetime.now()}
        if ip_address:
            vals["last_ip"] = ip_address
        device.sudo().write(vals)
        return device.user_id

    @api.model
    def revoke_bearer_token(self, plain_token):
        device = self._find_bearer_device(plain_token)
        if device:
            device.action_revoke_token()
            return True
        return False

    def action_reset_device(self):
        for rec in self:
            rec.sudo().write({
                "active": False,
                "device_uid": False,
                "device_name": False,
                "registered_ip": False,
                "last_ip": False,
                "token_hash": False,
                "token_index": False,
                "registered_at": False,
                "last_login": False,
                "token_expires_at": False,
            })

    def action_revoke_token(self):
        self.action_reset_device()


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    employee_app_device_ids = fields.One2many(
        "anabtawi.mobile.device",
        "employee_id",
        string="Employee App Devices",
        readonly=True,
    )
    employee_app_active_device_id = fields.Many2one(
        "anabtawi.mobile.device",
        string="Registered Employee App Device",
        compute="_compute_employee_app_active_device",
    )
    employee_app_device_uid = fields.Char(
        string="Employee App Device UID",
        compute="_compute_employee_app_active_device",
    )
    employee_app_device_name = fields.Char(
        string="Employee App Device Name",
        compute="_compute_employee_app_active_device",
    )
    employee_app_registered_ip = fields.Char(
        string="Registered IP",
        compute="_compute_employee_app_active_device",
    )
    employee_app_last_ip = fields.Char(
        string="Last IP",
        compute="_compute_employee_app_active_device",
    )
    employee_app_registered_at = fields.Datetime(
        string="Registered At",
        compute="_compute_employee_app_active_device",
    )
    employee_app_last_login = fields.Datetime(
        string="Last Login",
        compute="_compute_employee_app_active_device",
    )

    def _compute_employee_app_active_device(self):
        Device = self.env["anabtawi.mobile.device"].sudo()
        for employee in self:
            device = Device.search([
                ("user_id", "=", employee.user_id.id),
                ("active", "=", True),
            ], order="last_login desc, id desc", limit=1) if employee.user_id else Device.browse()
            employee.employee_app_active_device_id = device
            employee.employee_app_device_uid = device.device_uid or False
            employee.employee_app_device_name = device.device_name or False
            employee.employee_app_registered_ip = device.registered_ip or False
            employee.employee_app_last_ip = device.last_ip or False
            employee.employee_app_registered_at = device.registered_at or False
            employee.employee_app_last_login = device.last_login or False

    def action_reset_employee_app_device(self):
        for employee in self:
            devices = self.env["anabtawi.mobile.device"].sudo().search([
                ("user_id", "=", employee.user_id.id),
                ("active", "=", True),
            ]) if employee.user_id else self.env["anabtawi.mobile.device"].browse()
            devices.action_reset_device()
        return True
