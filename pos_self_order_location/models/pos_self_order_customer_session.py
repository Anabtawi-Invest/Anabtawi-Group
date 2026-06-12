# -*- coding: utf-8 -*-
import uuid
from datetime import timedelta

from odoo import api, fields, models


class PosSelfOrderCustomerSession(models.Model):
    _name = 'pos.self.order.customer.session'
    _description = 'Self-Order Customer Session'
    _order = 'create_date desc'

    token = fields.Char(required=True, index=True)
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade', index=True)
    config_id = fields.Many2one('pos.config', required=True, ondelete='cascade', index=True)
    phone = fields.Char(required=True, index=True)
    expires_at = fields.Datetime(required=True, index=True)

    @api.model
    def _gc_expired(self):
        self.search([('expires_at', '<', fields.Datetime.now())]).unlink()

    @api.model
    def create_session(self, partner, config, phone):
        self._gc_expired()
        token = str(uuid.uuid4())
        return self.create({
            'token': token,
            'partner_id': partner.id,
            'config_id': config.id,
            'phone': self.env['res.partner']._normalize_phone(phone),
            'expires_at': fields.Datetime.now() + timedelta(days=30),
        })

    @api.model
    def get_valid_session(self, token, config):
        if not token:
            return self.env['pos.self.order.customer.session']
        self._gc_expired()
        return self.search([
            ('token', '=', token),
            ('config_id', '=', config.id),
            ('expires_at', '>', fields.Datetime.now()),
        ], limit=1)
