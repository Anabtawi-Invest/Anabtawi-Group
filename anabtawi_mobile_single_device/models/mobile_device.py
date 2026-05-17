# -*- coding: utf-8 -*-

import hashlib
import hmac
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AnabtawiMobileDevice(models.Model):
    _name = 'anabtawi.mobile.device'
    _description = 'Registered mobile app device (one row per user)'

    user_id = fields.Many2one(
        'res.users', required=True, ondelete='cascade', index=True,
    )
    device_uid = fields.Char(string='Device UID', index=True)
    device_name = fields.Char()
    token_index = fields.Char(string='Token index', size=8, index=True)
    token_hash = fields.Char(string='Token hash', groups='base.group_system')
    active = fields.Boolean(default=True)
    last_login = fields.Datetime()

    _sql_constraints = [
        (
            'user_device_uid_unique',
            'unique(user_id, device_uid)',
            _('The same device is already registered for this user.'),
        ),
    ]

    @api.model
    def _get_pepper(self):
        return self.env['ir.config_parameter'].sudo().get_param('anabtawi_mobile.token_pepper') or ''

    @api.model
    def _hash_plain_token(self, plain_token):
        if not plain_token:
            return ''
        pepper = self._get_pepper().encode()
        return hmac.new(pepper, plain_token.encode(), hashlib.sha256).hexdigest()

    @api.model
    def _issue_plain_token(self):
        return secrets.token_urlsafe(32)

    @api.model
    def _get_allowed_devices_limit(self, user):
        """Return the max active devices for a user based on employee department."""
        limit = 1
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', user.id),
            ('active', '=', True),
        ], limit=1)
        if employee and employee.department_id and employee.department_id.mobile_device_limit:
            limit = employee.department_id.mobile_device_limit
        return max(1, int(limit))

    def _apply_new_tokens(self, plain_token):
        digest = self._hash_plain_token(plain_token)
        self.sudo().write({
            'token_hash': digest,
            'token_index': digest[:8] if digest else False,
            'last_login': fields.Datetime.now(),
            'active': True,
        })

    @api.model
    def register_or_refresh_login(self, user, device_uid_clean, device_name):
        """Password auth already succeeded. Returns a dict with ``access_token`` (plain) or raises UserError."""
        if not device_uid_clean:
            raise UserError(_('device_uid is required.'))

        self_sudo = self.sudo()
        allowed_limit = self_sudo._get_allowed_devices_limit(user)
        active_rows = self_sudo.search([
            ('user_id', '=', user.id),
            ('active', '=', True),
        ])
        active_same_device = active_rows.filtered(lambda r: r.device_uid == device_uid_clean)[:1]

        plain = self_sudo._issue_plain_token()
        if active_same_device:
            row_sudo = active_same_device.sudo()
            row_sudo.write({
                'device_name': device_name if device_name else row_sudo.device_name,
            })
            row_sudo._apply_new_tokens(plain)
            return {'access_token': plain}

        if len(active_rows) >= allowed_limit:
            raise UserError(_(
                'You reached your department device limit (%s). '
                'Ask an administrator to reset one of your registered devices.'
            ) % allowed_limit)

        row = self_sudo.search([
            ('user_id', '=', user.id),
            ('device_uid', '=', device_uid_clean),
        ], limit=1)
        if row:
            row_sudo = row.sudo()
            row_sudo.write({
                'device_name': device_name if device_name else row_sudo.device_name,
            })
            row_sudo._apply_new_tokens(plain)
            return {'access_token': plain}

        digest = self_sudo._hash_plain_token(plain)
        self_sudo.create({
            'user_id': user.id,
            'device_uid': device_uid_clean,
            'device_name': device_name or '',
            'token_hash': digest,
            'token_index': digest[:8] if digest else False,
            'active': True,
            'last_login': fields.Datetime.now(),
        })
        return {'access_token': plain}

    @api.model
    def authenticate_bearer_token(self, plain_token):
        """Return ``res.users`` recordset (singleton or empty) if token is valid."""
        self_sudo = self.sudo()
        if not plain_token:
            return self.env['res.users']

        digest = self_sudo._hash_plain_token(plain_token)
        if not digest:
            return self.env['res.users']

        idx = digest[:8]
        candidates = self_sudo.search([('token_index', '=', idx), ('active', '=', True)])
        for device in candidates:
            if device.token_hash and hmac.compare_digest(device.token_hash, digest):
                device.sudo().write({'last_login': fields.Datetime.now()})
                return device.user_id
        return self.env['res.users']

    def action_reset_device(self):
        for rec in self:
            rec.sudo().write({
                'active': False,
                'device_uid': False,
                'device_name': False,
                'token_hash': False,
                'token_index': False,
                'last_login': False,
            })

    def action_revoke_token(self):
        self.action_reset_device()
