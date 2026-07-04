import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AnabtawiMobileDevice(models.Model):
    _name = "anabtawi.mobile.device"
    _description = "Registered Employee App device"
    _order = "last_login desc, id desc"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    device_uid = fields.Char(string="Device UUID", index=True)
    device_name = fields.Char()
    platform = fields.Char()
    manufacturer = fields.Char()
    model_name = fields.Char(string="Model")
    app_version = fields.Char(string="App Version")
    registered_ip = fields.Char(string="Registered IP", readonly=True)
    token_index = fields.Char(string="Access Token Index", size=8, index=True)
    token_hash = fields.Char(string="Access Token Hash", groups="base.group_system")
    token_expires_at = fields.Datetime(string="Access Token Expires At", readonly=True, index=True)
    refresh_token_index = fields.Char(string="Refresh Token Index", size=8, index=True)
    refresh_token_hash = fields.Char(string="Refresh Token Hash", groups="base.group_system")
    refresh_token_expires_at = fields.Datetime(string="Refresh Token Expires At", readonly=True, index=True)
    active = fields.Boolean(default=True, index=True)
    last_login = fields.Datetime(readonly=True)

    _sql_constraints = [(
        "user_device_uid_unique",
        "unique(user_id, device_uid)",
        "The same device is already registered for this user.",
    )]

    @api.model
    def _get_pepper(self):
        return self.env["ir.config_parameter"].sudo().get_param("anabtawi_mobile.token_pepper") or ""

    @api.model
    def _hash_plain_token(self, plain_token):
        if not plain_token:
            return ""
        return hmac.new(self._get_pepper().encode(), plain_token.encode(), hashlib.sha256).hexdigest()

    @api.model
    def _access_token_ttl_minutes(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "anabtawi_mobile.access_token_ttl_minutes", "60"
        )
        try:
            return max(5, min(int(raw), 1440))
        except (TypeError, ValueError):
            return 60

    @api.model
    def _refresh_token_ttl_days(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "anabtawi_mobile.refresh_token_ttl_days", "30"
        )
        try:
            return max(1, min(int(raw), 365))
        except (TypeError, ValueError):
            return 30

    @api.model
    def _new_token_pair(self):
        return secrets.token_urlsafe(32), secrets.token_urlsafe(48)

    def _write_token_pair(self, access_token, refresh_token):
        self.ensure_one()
        access_hash = self._hash_plain_token(access_token)
        refresh_hash = self._hash_plain_token(refresh_token)
        now = fields.Datetime.now()
        self.sudo().write({
            "token_hash": access_hash,
            "token_index": access_hash[:8],
            "token_expires_at": now + timedelta(minutes=self._access_token_ttl_minutes()),
            "refresh_token_hash": refresh_hash,
            "refresh_token_index": refresh_hash[:8],
            "refresh_token_expires_at": now + timedelta(days=self._refresh_token_ttl_days()),
            "last_login": now,
            "active": True,
        })
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": self._access_token_ttl_minutes() * 60,
        }

    def _device_values(self, device_data=None, registered_ip=None):
        data = device_data or {}
        values = {
            "device_name": (data.get("device_name") or "Mobile device")[:128],
            "platform": (data.get("platform") or "")[:64],
            "manufacturer": (data.get("manufacturer") or "")[:128],
            "model_name": (data.get("model_name") or "")[:128],
            "app_version": (data.get("app_version") or "")[:32],
        }
        if registered_ip:
            values["registered_ip"] = str(registered_ip)[:64]
        return values

    @api.model
    def register_or_refresh_login(self, user, device_uid, device_data=None, registered_ip=None):
        device_uid = (device_uid or "").strip()
        if not device_uid:
            raise UserError(_("Device UUID is required."))
        Device = self.sudo()
        active_devices = Device.search([("user_id", "=", user.id), ("active", "=", True)])
        other_device = active_devices.filtered(lambda item: item.device_uid != device_uid)[:1]
        if other_device:
            raise UserError(_(
                "This employee is already registered on another device. "
                "Ask HR to reset the Employee App device."
            ))
        device = active_devices.filtered(lambda item: item.device_uid == device_uid)[:1]
        if not device:
            device = Device.search([
                ("user_id", "=", user.id), ("device_uid", "=", device_uid)
            ], limit=1)
        values = self._device_values(device_data, registered_ip)
        if device:
            device.write(values)
        else:
            device = Device.create({"user_id": user.id, "device_uid": device_uid, **values})
        return device._write_token_pair(*self._new_token_pair())

    @api.model
    def _find_token_device(self, plain_token, refresh=False):
        digest = self.sudo()._hash_plain_token(plain_token)
        if not digest:
            return self.browse()
        prefix = "refresh_token" if refresh else "token"
        candidates = self.sudo().search([
            (f"{prefix}_index", "=", digest[:8]), ("active", "=", True)
        ])
        return candidates.filtered(
            lambda item: item[f"{prefix}_hash"]
            and hmac.compare_digest(item[f"{prefix}_hash"], digest)
        )[:1]

    @api.model
    def authenticate_bearer_token(self, plain_token):
        device = self._find_token_device(plain_token)
        if not device or not device.user_id.active:
            return self.env["res.users"]
        if device.token_expires_at and device.token_expires_at <= fields.Datetime.now():
            device.sudo().write({"token_hash": False, "token_index": False, "token_expires_at": False})
            return self.env["res.users"]
        device.sudo().write({"last_login": fields.Datetime.now()})
        return device.user_id

    @api.model
    def refresh_login(self, refresh_token, device_uid, device_data=None, registered_ip=None):
        device = self._find_token_device(refresh_token, refresh=True)
        if not device or not device.user_id.active:
            raise UserError(_("The refresh token is invalid."))
        if device.refresh_token_expires_at and device.refresh_token_expires_at <= fields.Datetime.now():
            device.action_reset_device()
            raise UserError(_("The refresh token has expired. Please sign in again."))
        if device.device_uid != (device_uid or "").strip():
            raise UserError(_("The refresh token does not belong to this device."))
        device.write(device._device_values(device_data, registered_ip))
        return device._write_token_pair(*self._new_token_pair())

    @api.model
    def revoke_bearer_token(self, plain_token):
        device = self._find_token_device(plain_token)
        if device:
            device.action_reset_device()
            return True
        return False

    def action_reset_device(self):
        self.sudo().write({
            "active": False,
            "device_uid": False,
            "token_hash": False,
            "token_index": False,
            "token_expires_at": False,
            "refresh_token_hash": False,
            "refresh_token_index": False,
            "refresh_token_expires_at": False,
        })
