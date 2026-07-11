import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models


class AnabtawiApiToken(models.Model):
    _name = "anabtawi.api.token"
    _description = "Simple API Access Token"
    _rec_name = "user_id"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    token_index = fields.Char(size=8, index=True)
    token_hash = fields.Char(groups="base.group_system")
    active = fields.Boolean(default=True)
    expires_at = fields.Datetime(required=True, index=True)
    last_used_at = fields.Datetime()

    @api.model
    def _get_pepper(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "anabtawi_simple_api.token_pepper"
        ) or "anabtawi-simple-api"

    @api.model
    def _hash_token(self, plain_token):
        pepper = self._get_pepper().encode()
        return hmac.new(pepper, (plain_token or "").encode(), hashlib.sha256).hexdigest()

    @api.model
    def _token_ttl_days(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "anabtawi_simple_api.token_ttl_days", "30"
        )
        try:
            return max(1, min(int(raw), 365))
        except (TypeError, ValueError):
            return 30

    @api.model
    def issue_token(self, user):
        """Create a new API token for the user and return the plain token."""
        plain = secrets.token_urlsafe(32)
        digest = self._hash_token(plain)
        self.sudo().create({
            "user_id": user.id,
            "token_hash": digest,
            "token_index": digest[:8],
            "expires_at": fields.Datetime.now() + timedelta(days=self._token_ttl_days()),
            "active": True,
        })
        return plain

    @api.model
    def authenticate_token(self, plain_token):
        """Return the user for a valid token, otherwise an empty recordset."""
        if not plain_token:
            return self.env["res.users"]

        digest = self._hash_token(plain_token)
        token = self.sudo().search([
            ("token_index", "=", digest[:8]),
            ("token_hash", "=", digest),
            ("active", "=", True),
            ("expires_at", ">", fields.Datetime.now()),
        ], limit=1)
        if not token or not token.user_id.active:
            return self.env["res.users"]

        token.sudo().write({"last_used_at": fields.Datetime.now()})
        return token.user_id
