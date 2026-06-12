# -*- coding: utf-8 -*-
import random
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosSelfOrderPhoneOtp(models.Model):
    _name = 'pos.self.order.phone.otp'
    _description = 'Self-Order Phone OTP'
    _order = 'create_date desc'

    phone = fields.Char(required=True, index=True)
    config_id = fields.Many2one('pos.config', required=True, ondelete='cascade', index=True)
    code = fields.Char(required=True)
    expires_at = fields.Datetime(required=True, index=True)
    consumed = fields.Boolean(default=False, index=True)

    @api.model
    def _gc_expired(self):
        timeout = fields.Datetime.now() - timedelta(days=1)
        self.search([('create_date', '<', timeout)]).unlink()

    @api.model
    def generate_for_phone(self, phone, config):
        self._gc_expired()
        normalized = self.env['res.partner']._normalize_phone(phone)
        self.search([
            ('phone', '=', normalized),
            ('config_id', '=', config.id),
            ('consumed', '=', False),
        ]).write({'consumed': True})

        code = f'{random.randint(0, 999999):06d}'
        return self.create({
            'phone': normalized,
            'config_id': config.id,
            'code': code,
            'expires_at': fields.Datetime.now() + timedelta(minutes=10),
        })

    @api.model
    def verify(self, phone, code, config):
        normalized = self.env['res.partner']._normalize_phone(phone)
        otp = self.search([
            ('phone', '=', normalized),
            ('config_id', '=', config.id),
            ('consumed', '=', False),
            ('expires_at', '>', fields.Datetime.now()),
        ], order='create_date desc', limit=1)
        if not otp or otp.code != str(code).strip():
            raise UserError(_('Invalid or expired verification code.'))
        otp.consumed = True
        return True
