# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AnabtawiTalabatConfig(models.Model):
    _name = 'anabtawi.talabat.config'
    _description = 'Talabat Connector Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(required=True, default='Talabat')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    environment = fields.Selection([('sandbox', 'Sandbox'), ('production', 'Production')], default='sandbox', required=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    api_base_url = fields.Char(required=True, default='https://api.talabat.com')
    auth_url = fields.Char(string='OAuth Token URL')
    client_id = fields.Char(copy=False)
    client_secret = fields.Char(copy=False)
    chain_id = fields.Char(copy=False)
    webhook_secret = fields.Char(copy=False, help='Shared secret used by the webhook URL for basic validation.')
    access_token = fields.Text(copy=False, readonly=True)
    token_expiry = fields.Datetime(copy=False, readonly=True)
    auto_accept_orders = fields.Boolean(default=False)
    create_sale_order_on_import = fields.Boolean(default=False)
    default_branch_id = fields.Many2one('anabtawi.ordering.branch', string='Fallback Branch')
    default_payment_method = fields.Selection([('aggregator', 'Aggregator Settlement'), ('online', 'Online'), ('cash', 'Cash')], default='aggregator')
    last_connection_status = fields.Selection([('not_tested', 'Not Tested'), ('success', 'Success'), ('failed', 'Failed')], default='not_tested', readonly=True)
    last_connection_message = fields.Text(readonly=True)

    def _get_headers(self):
        self.ensure_one()
        token = self.access_token
        if not token or (self.token_expiry and self.token_expiry <= fields.Datetime.now()):
            self.action_refresh_token()
            token = self.access_token
        return {
            'Authorization': 'Bearer %s' % token,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def _request(self, method, endpoint, payload=None, params=None):
        self.ensure_one()
        if requests is None:
            raise UserError(_('Python requests library is not available on this server.'))
        url = '%s/%s' % ((self.api_base_url or '').rstrip('/'), (endpoint or '').lstrip('/'))
        log = self.env['anabtawi.talabat.api.log'].sudo().create({
            'config_id': self.id,
            'method': method,
            'endpoint': endpoint,
            'request_payload': json.dumps(payload or params or {}, ensure_ascii=False),
        })
        try:
            response = requests.request(method, url, headers=self._get_headers(), json=payload, params=params, timeout=30)
            text = response.text or ''
            log.write({
                'status_code': response.status_code,
                'response_payload': text[:20000],
                'state': 'success' if 200 <= response.status_code < 300 else 'failed',
            })
            if response.status_code >= 300:
                raise UserError(_('Talabat API error %(code)s: %(body)s') % {'code': response.status_code, 'body': text[:500]})
            return response.json() if text else {}
        except Exception as exc:
            log.write({'state': 'failed', 'response_payload': str(exc)[:20000]})
            raise

    def action_refresh_token(self):
        for config in self:
            if not config.auth_url:
                raise UserError(_('Please set the Talabat OAuth Token URL.'))
            if not config.client_id or not config.client_secret:
                raise UserError(_('Please set Talabat client_id and client_secret.'))
            if requests is None:
                raise UserError(_('Python requests library is not available on this server.'))
            try:
                response = requests.post(config.auth_url, data={
                    'grant_type': 'client_credentials',
                    'client_id': config.client_id,
                    'client_secret': config.client_secret,
                }, timeout=30)
                data = response.json() if response.text else {}
                if response.status_code >= 300:
                    raise UserError(response.text)
                token = data.get('access_token')
                if not token:
                    raise UserError(_('Talabat did not return access_token.'))
                expires_in = int(data.get('expires_in') or 3600)
                config.write({
                    'access_token': token,
                    'token_expiry': fields.Datetime.now() + timedelta(seconds=max(expires_in - 120, 60)),
                    'last_connection_status': 'success',
                    'last_connection_message': _('Token refreshed successfully.'),
                })
            except Exception as exc:
                config.write({'last_connection_status': 'failed', 'last_connection_message': str(exc)})
                raise
        return True

    def action_test_connection(self):
        for config in self:
            try:
                config.action_refresh_token()
                config.write({'last_connection_status': 'success', 'last_connection_message': _('Connection successful.')})
            except Exception as exc:
                config.write({'last_connection_status': 'failed', 'last_connection_message': str(exc)})
                raise
        return True

    def action_pull_orders(self):
        for config in self:
            data = config._request('GET', '/orders', params={'chain_id': config.chain_id} if config.chain_id else {})
            orders = data.get('orders') if isinstance(data, dict) else data
            for payload in orders or []:
                config._create_or_update_order_from_payload(payload)
        return True

    def _create_or_update_order_from_payload(self, payload):
        self.ensure_one()
        external_ref = str(payload.get('order_id') or payload.get('id') or payload.get('code') or '')
        if not external_ref:
            raise UserError(_('Talabat payload is missing order id.'))
        existing = self.env['anabtawi.direct.order'].sudo().search([('channel', '=', 'talabat'), ('external_order_ref', '=', external_ref)], limit=1)
        vals = self._prepare_direct_order_vals(payload)
        if existing:
            existing.write({
                'raw_payload': json.dumps(payload, ensure_ascii=False),
                'talabat_status': payload.get('status') or existing.talabat_status,
            })
            return existing
        order = self.env['anabtawi.direct.order'].sudo().create(vals)
        if self.auto_accept_orders:
            order.action_accept()
            order.action_push_talabat_status()
        if self.create_sale_order_on_import:
            order.action_create_sale_order()
        return order

    def _prepare_direct_order_vals(self, payload):
        external_ref = str(payload.get('order_id') or payload.get('id') or payload.get('code'))
        vendor_id = str(payload.get('vendor_id') or payload.get('restaurant_id') or payload.get('branch_id') or '')
        branch = self.env['anabtawi.talabat.branch.map'].sudo().search([('config_id', '=', self.id), ('talabat_vendor_id', '=', vendor_id)], limit=1).branch_id or self.default_branch_id
        if not branch:
            raise UserError(_('No Anabtawi branch mapping found for Talabat vendor ID: %s') % vendor_id)
        customer = payload.get('customer') or {}
        address = payload.get('delivery_address') or payload.get('address') or {}
        totals = payload.get('totals') or payload.get('amounts') or {}
        lines = []
        for item in payload.get('items') or []:
            product = self._map_product(item)
            qty = float(item.get('quantity') or item.get('qty') or 1.0)
            unit_price = float(item.get('unit_price') or item.get('price') or item.get('total_price') or product.lst_price or 0.0)
            discount_amount = float(item.get('discount_amount') or item.get('discount') or 0.0)
            discount_percent = (discount_amount / (unit_price * qty) * 100.0) if unit_price and qty and discount_amount else 0.0
            lines.append((0, 0, {
                'product_id': product.id,
                'name': item.get('name') or product.display_name,
                'quantity': qty,
                'price_unit': unit_price,
                'discount_percent': discount_percent,
                'external_line_ref': str(item.get('id') or item.get('sku') or ''),
                'notes': item.get('notes') or item.get('special_instructions'),
            }))
        order_type = 'delivery' if (payload.get('delivery_type') or payload.get('order_type') or '').lower() != 'pickup' else 'pickup'
        return {
            'channel': 'talabat',
            'talabat_config_id': self.id,
            'external_order_ref': external_ref,
            'talabat_vendor_id': vendor_id,
            'talabat_status': payload.get('status'),
            'branch_id': branch.id,
            'customer_name': customer.get('name') or payload.get('customer_name') or 'Talabat Customer',
            'customer_phone': customer.get('phone') or payload.get('customer_phone') or 'N/A',
            'customer_address': address.get('line1') or address.get('address') or payload.get('customer_address'),
            'order_type': order_type,
            'payment_method': self.default_payment_method,
            'notes': payload.get('notes') or payload.get('comment'),
            'raw_payload': json.dumps(payload, ensure_ascii=False),
            'talabat_commission_amount': float(totals.get('commission') or payload.get('commission') or 0.0),
            'talabat_commission_percent': float(totals.get('commission_percent') or payload.get('commission_percent') or 0.0),
            'aggregator_discount_amount': float(totals.get('talabat_discount') or totals.get('aggregator_discount') or 0.0),
            'company_discount_amount': float(totals.get('vendor_discount') or totals.get('company_discount') or 0.0),
            'line_ids': lines,
        }

    def _map_product(self, item):
        talabat_item_id = str(item.get('id') or item.get('item_id') or '')
        sku = str(item.get('sku') or item.get('vendor_sku') or '')
        mapping = self.env['anabtawi.talabat.product.map'].sudo().search([
            ('config_id', '=', self.id), '|', ('talabat_item_id', '=', talabat_item_id), ('talabat_sku', '=', sku)
        ], limit=1)
        if not mapping or not mapping.product_id:
            raise UserError(_('No product mapping found for Talabat item %(item)s / SKU %(sku)s') % {'item': talabat_item_id, 'sku': sku})
        return mapping.product_id


class AnabtawiTalabatBranchMap(models.Model):
    _name = 'anabtawi.talabat.branch.map'
    _description = 'Talabat Branch Mapping'
    _rec_name = 'talabat_vendor_id'

    config_id = fields.Many2one('anabtawi.talabat.config', required=True, ondelete='cascade')
    talabat_vendor_id = fields.Char(required=True, index=True)
    talabat_vendor_name = fields.Char()
    branch_id = fields.Many2one('anabtawi.ordering.branch', required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('talabat_vendor_unique', 'unique(config_id, talabat_vendor_id)', 'Talabat vendor ID must be unique per configuration.'),
    ]


class AnabtawiTalabatProductMap(models.Model):
    _name = 'anabtawi.talabat.product.map'
    _description = 'Talabat Product Mapping'
    _rec_name = 'product_id'

    config_id = fields.Many2one('anabtawi.talabat.config', required=True, ondelete='cascade')
    talabat_item_id = fields.Char(index=True)
    talabat_sku = fields.Char(index=True)
    talabat_item_name = fields.Char()
    product_id = fields.Many2one('product.product', required=True)
    active = fields.Boolean(default=True)
    sync_availability = fields.Boolean(default=True)

    @api.constrains('talabat_item_id', 'talabat_sku')
    def _check_identifier(self):
        for rec in self:
            if not rec.talabat_item_id and not rec.talabat_sku:
                raise ValidationError(_('Set either Talabat Item ID or Talabat SKU.'))

    def action_push_availability(self):
        for mapping in self:
            if not mapping.sync_availability:
                continue
            payload = {
                'item_id': mapping.talabat_item_id,
                'sku': mapping.talabat_sku,
                'available': mapping.product_id.qty_available > 0,
            }
            mapping.config_id._request('POST', '/products/availability', payload=payload)
        return True


class AnabtawiTalabatApiLog(models.Model):
    _name = 'anabtawi.talabat.api.log'
    _description = 'Talabat API Log'
    _order = 'create_date desc, id desc'

    config_id = fields.Many2one('anabtawi.talabat.config', ondelete='set null')
    method = fields.Char()
    endpoint = fields.Char()
    status_code = fields.Integer()
    state = fields.Selection([('success', 'Success'), ('failed', 'Failed')], default='success')
    request_payload = fields.Text()
    response_payload = fields.Text()
