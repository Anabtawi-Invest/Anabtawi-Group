# -*- coding: utf-8 -*-

import hashlib
import hmac
import secrets
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import STORED_SESSION_BYTES

_logger = logging.getLogger(__name__)


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
        _logger.info(
            "Mobile auth limit resolved: user_id=%s employee_id=%s department_id=%s department_name=%s limit=%s",
            user.id,
            employee.id if employee else None,
            employee.department_id.id if employee and employee.department_id else None,
            employee.department_id.name if employee and employee.department_id else None,
            limit,
        )
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
            _logger.warning("Mobile auth rejected: missing device_uid for user_id=%s", user.id)
            raise UserError(_('device_uid is required.'))

        self_sudo = self.sudo()
        allowed_limit = self_sudo._get_allowed_devices_limit(user)
        active_rows = self_sudo.search([
            ('user_id', '=', user.id),
            ('active', '=', True),
        ])
        active_same_device = active_rows.filtered(lambda r: r.device_uid == device_uid_clean)[:1]
        _logger.info(
            "Mobile auth register attempt: user_id=%s device_uid=%s active_devices=%s limit=%s",
            user.id,
            device_uid_clean,
            len(active_rows),
            allowed_limit,
        )

        plain = self_sudo._issue_plain_token()
        if active_same_device:
            row_sudo = active_same_device.sudo()
            _logger.info(
                "Mobile auth refreshing existing device: user_id=%s record_id=%s device_uid=%s",
                user.id,
                row_sudo.id,
                device_uid_clean,
            )
            row_sudo.write({
                'device_name': device_name if device_name else row_sudo.device_name,
            })
            row_sudo._apply_new_tokens(plain)
            return {'access_token': plain}

        if len(active_rows) >= allowed_limit:
            _logger.warning(
                "Mobile auth rejected by device limit: user_id=%s device_uid=%s active_devices=%s limit=%s",
                user.id,
                device_uid_clean,
                len(active_rows),
                allowed_limit,
            )
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
            _logger.info(
                "Mobile auth reactivating known device record: user_id=%s record_id=%s device_uid=%s",
                user.id,
                row_sudo.id,
                device_uid_clean,
            )
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
        _logger.info(
            "Mobile auth created new device record: user_id=%s device_uid=%s active_devices_before=%s limit=%s",
            user.id,
            device_uid_clean,
            len(active_rows),
            allowed_limit,
        )
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


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    mobile_device_limit = fields.Integer(
        string='Mobile Device Limit',
        default=1,
        help='Maximum number of active mobile devices allowed for users in this department.',
    )

    @api.constrains('mobile_device_limit')
    def _check_mobile_device_limit(self):
        for rec in self:
            if rec.mobile_device_limit < 1:
                raise ValidationError(_('Mobile Device Limit must be at least 1.'))


class ResDeviceLog(models.Model):
    _inherit = 'res.device.log'

    def _eligible_mobile_user(self, user):
        if not user or not user.active:
            return False
        u = user.with_user(user)
        if u.has_group('base.group_public') and not u.has_group('base.group_portal') and not u.has_group('base.group_user'):
            return False
        return u.has_group('base.group_portal') or u.has_group('base.group_user')

    @api.model
    def _update_device(self, request):
        super()._update_device(request)
        if not request or not request.session or not request.session.uid:
            return

        user = self.env['res.users'].sudo().browse(request.session.uid)
        if not self._eligible_mobile_user(user):
            return

        allowed_limit = self.env['anabtawi.mobile.device']._get_allowed_devices_limit(user)
        current_session_identifier = request.session.sid[:STORED_SESSION_BYTES]
        devices = self.env['res.device'].sudo().search([
            ('user_id', '=', user.id),
            ('device_type', '=', 'mobile'),
        ], order='last_activity desc')
        _logger.info(
            "Web login device limit check: user_id=%s mobile_devices=%s limit=%s current_session=%s",
            user.id,
            len(devices),
            allowed_limit,
            current_session_identifier,
        )

        if len(devices) <= allowed_limit:
            return

        current_device = devices.filtered(lambda d: d.session_identifier == current_session_identifier)[:1]
        _logger.warning(
            "Web login rejected by department device limit: user_id=%s mobile_devices=%s limit=%s session=%s",
            user.id,
            len(devices),
            allowed_limit,
            current_session_identifier,
        )
        if current_device:
            current_device._revoke()
        else:
            request.session.logout()
