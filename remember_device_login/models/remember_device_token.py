# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class RememberDeviceToken(models.Model):
    _name = "remember.device.token"
    _description = "Remember Device Token"
    _rec_name = "user_id"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    token_index = fields.Char(index=True, required=True)
    token_hash = fields.Char(required=True)
    device_fingerprint = fields.Char(index=True)
    expires_at = fields.Datetime(required=True, index=True)
    last_used_at = fields.Datetime()
    active = fields.Boolean(default=True, index=True)

    @api.model
    def _cookie_name(self):
        return "anabtawi_remember_device"

    @api.model
    def _cookie_max_age(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            "remember_device_login.max_age_days", default="90"
        )
        try:
            days = max(int(value or 90), 1)
        except (TypeError, ValueError):
            days = 90
        return days * 24 * 60 * 60

    @api.model
    def _expires_at(self):
        return fields.Datetime.now() + timedelta(seconds=self._cookie_max_age())

    @api.model
    def _pepper(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            "remember_device_login.token_pepper"
        ) or self.env["ir.config_parameter"].sudo().get_param("database.secret") or ""
        return value.encode()

    @api.model
    def _hash_token(self, plain_token):
        if not plain_token:
            return ""
        return hmac.new(self._pepper(), plain_token.encode(), hashlib.sha256).hexdigest()

    @api.model
    def issue_for_user(self, user, device_fingerprint):
        plain = secrets.token_urlsafe(48)
        digest = self._hash_token(plain)
        vals = {
            "user_id": user.id,
            "token_hash": digest,
            "token_index": digest[:12],
            "device_fingerprint": device_fingerprint or "",
            "expires_at": self._expires_at(),
            "last_used_at": fields.Datetime.now(),
            "active": True,
        }
        # Keep one active token per user/device to avoid unbounded growth.
        existing = self.sudo().search(
            [
                ("user_id", "=", user.id),
                ("device_fingerprint", "=", device_fingerprint or ""),
                ("active", "=", True),
            ]
        )
        if existing:
            existing.write(vals)
        else:
            self.sudo().create(vals)
        _logger.info(
            "remember_device_login token issued: user_id=%s fingerprint=%s",
            user.id,
            device_fingerprint or "",
        )
        return plain

    @api.model
    def authenticate_cookie(self, plain_token, device_fingerprint):
        digest = self._hash_token(plain_token)
        if not digest:
            return self.env["res.users"]
        now = fields.Datetime.now()
        candidates = self.sudo().search(
            [
                ("token_index", "=", digest[:12]),
                ("active", "=", True),
                ("expires_at", ">", now),
            ]
        )
        for rec in candidates:
            if rec.device_fingerprint and rec.device_fingerprint != (device_fingerprint or ""):
                continue
            if rec.token_hash and hmac.compare_digest(rec.token_hash, digest):
                rec.write({"last_used_at": now})
                return rec.user_id
        return self.env["res.users"]

    @api.model
    def revoke_cookie(self, plain_token):
        digest = self._hash_token(plain_token)
        if not digest:
            return
        recs = self.sudo().search(
            [
                ("token_index", "=", digest[:12]),
                ("active", "=", True),
            ]
        )
        for rec in recs:
            if rec.token_hash and hmac.compare_digest(rec.token_hash, digest):
                rec.write({"active": False})

    @api.model
    def cron_cleanup_expired_tokens(self):
        expired = self.sudo().search(
            [("active", "=", True), ("expires_at", "<=", fields.Datetime.now())]
        )
        if expired:
            expired.write({"active": False})
        _logger.info(
            "remember_device_login cleanup done: deactivated=%s",
            len(expired),
        )
