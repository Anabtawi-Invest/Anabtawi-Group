import hmac
from datetime import timedelta

from odoo import api, fields, models


class AnabtawiMobileDevice(models.Model):
    _inherit = "anabtawi.mobile.device"

    token_expires_at = fields.Datetime(
        string="Token Expires At",
        readonly=True,
        index=True,
    )

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
        result = super()._apply_new_tokens(plain_token)
        self.sudo().write({
            "token_expires_at": fields.Datetime.now() + timedelta(days=self._token_ttl_days())
        })
        return result

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
        result = super().action_reset_device()
        self.sudo().write({"token_expires_at": False})
        return result

