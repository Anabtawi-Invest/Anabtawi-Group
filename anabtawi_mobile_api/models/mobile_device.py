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
    _description = "Registered mobile app device"

    user_id = fields.Many2one(
        "res.users", required=True, ondelete="cascade", index=True
    )
    device_uid = fields.Char(string="Device UID", index=True)
    device_name = fields.Char()
    token_index = fields.Char(string="Token index", size=8, index=True)
    token_hash = fields.Char(string="Token hash", groups="base.group_system")
    active = fields.Boolean(default=True)
    last_login = fields.Datetime()
    token_expires_at = fields.Datetime(
        string="Token Expires At",
        readonly=True,
        index=True,
    )

    _sql_constraints = [
        (
            "user_device_uid_unique",
            "unique(user_id, device_uid)",
            "The same device is already registered for this user.",
        ),
    ]

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

    def _apply_new_tokens(self, plain_token):
        digest = self._hash_plain_token(plain_token)
        self.sudo().write({
            "token_hash": digest,
            "token_index": digest[:8] if digest else False,
            "last_login": fields.Datetime.now(),
            "active": True,
            "token_expires_at": fields.Datetime.now() + timedelta(days=self._token_ttl_days()),
        })

    @api.model
    def register_or_refresh_login(self, user, device_uid_clean, device_name):
        if not device_uid_clean:
            raise UserError(_("device_uid is required."))
        self_sudo = self.sudo()

        # Enforce single-device restriction:
        # Search for any active device registered for this user
        active_devices = self_sudo.search([
            ("user_id", "=", user.id),
            ("active", "=", True),
        ])

        # If there's an active device and its device_uid is different, block login
        active_other_devices = active_devices.filtered(lambda d: d.device_uid != device_uid_clean)
        if active_other_devices:
            _logger.warning(
                "Mobile login rejected by single device constraint: user_id=%s device_uid=%s active_device_uid=%s",
                user.id,
                device_uid_clean,
                active_other_devices[0].device_uid,
            )
            raise UserError(_(
                "You have reached the maximum allowed devices (1). "
                "Please contact your system administrator to reset your registered device."
            ))

        active_same_device = active_devices.filtered(lambda d: d.device_uid == device_uid_clean)[:1]

        plain = self_sudo._issue_plain_token()
        if active_same_device:
            active_same_device.write({
                "device_name": device_name or active_same_device.device_name,
            })
            active_same_device._apply_new_tokens(plain)
            return {"access_token": plain}

        inactive_device = self_sudo.search([
            ("user_id", "=", user.id),
            ("device_uid", "=", device_uid_clean),
        ], limit=1)
        if inactive_device:
            inactive_device.write({
                "device_name": device_name or inactive_device.device_name,
                "active": True,
            })
            inactive_device._apply_new_tokens(plain)
            return {"access_token": plain}

        digest = self_sudo._hash_plain_token(plain)
        self_sudo.create({
            "user_id": user.id,
            "device_uid": device_uid_clean,
            "device_name": device_name or "",
            "token_hash": digest,
            "token_index": digest[:8] if digest else False,
            "active": True,
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
    def authenticate_bearer_token(self, plain_token):
        device = self._find_bearer_device(plain_token)
        if not device:
            return self.env["res.users"]
        if device.token_expires_at and device.token_expires_at <= fields.Datetime.now():
            device.action_revoke_token()
            return self.env["res.users"]
        if not device.user_id.active:
            device.action_revoke_token()
            return self.env["res.users"]
        device.sudo().write({"last_login": fields.Datetime.now()})
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
                "token_hash": False,
                "token_index": False,
                "last_login": False,
                "token_expires_at": False,
            })

    def action_revoke_token(self):
        self.action_reset_device()

