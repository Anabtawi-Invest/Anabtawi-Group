import json
from odoo import http
from odoo.http import request


class AnabtawiDirectOrderingController(http.Controller):

    @http.route('/anabtawi/ordering/branches', type='json', auth='public', methods=['POST'], csrf=False)
    def branches(self, **kwargs):
        branches = request.env['anabtawi.ordering.branch'].sudo().search([('active', '=', True)])
        return [{'id': b.id, 'name': b.name, 'allow_delivery': b.allow_delivery, 'allow_pickup': b.allow_pickup} for b in branches]

    @http.route('/anabtawi/ordering/menu', type='json', auth='public', methods=['POST'], csrf=False)
    def menu(self, **kwargs):
        products = request.env['product.product'].sudo().search([('product_tmpl_id.available_for_direct_ordering', '=', True), ('sale_ok', '=', True)])
        return [{
            'id': p.id,
            'name': p.product_tmpl_id.direct_ordering_name or p.display_name,
            'description': p.product_tmpl_id.direct_ordering_description or '',
            'category': p.product_tmpl_id.direct_ordering_category or '',
            'price': p.lst_price,
        } for p in products]

    @http.route('/anabtawi/ordering/create', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **payload):
        data = payload or {}
        if not data.get('branch_id') or not data.get('customer_name') or not data.get('customer_phone'):
            return {'success': False, 'error': 'Missing branch_id, customer_name, or customer_phone'}
        lines = []
        for item in data.get('lines', []):
            product = request.env['product.product'].sudo().browse(int(item.get('product_id')))
            if not product.exists():
                continue
            lines.append((0, 0, {
                'product_id': product.id,
                'name': item.get('name') or product.display_name,
                'quantity': float(item.get('quantity') or 1.0),
                'price_unit': float(item.get('price_unit', product.lst_price)),
                'discount_percent': float(item.get('discount_percent') or 0.0),
                'notes': item.get('notes'),
                'external_line_ref': item.get('external_line_ref'),
            }))
        order = request.env['anabtawi.direct.order'].sudo().create({
            'channel': data.get('channel') or 'direct_app',
            'external_order_ref': data.get('external_order_ref'),
            'branch_id': int(data['branch_id']),
            'customer_name': data['customer_name'],
            'customer_phone': data['customer_phone'],
            'customer_address': data.get('customer_address'),
            'order_type': data.get('order_type') or 'delivery',
            'payment_method': data.get('payment_method') or 'cash',
            'notes': data.get('notes'),
            'kitchen_notes': data.get('kitchen_notes'),
            'raw_payload': json.dumps(data, ensure_ascii=False),
            'line_ids': lines,
        })
        return {'success': True, 'order_id': order.id, 'order_name': order.name, 'state': order.state, 'amount_total': order.amount_total}

    @http.route('/anabtawi/ordering/status', type='json', auth='public', methods=['POST'], csrf=False)
    def order_status(self, **payload):
        domain = []
        if payload.get('order_id'):
            domain.append(('id', '=', int(payload['order_id'])))
        elif payload.get('external_order_ref'):
            domain.append(('external_order_ref', '=', payload['external_order_ref']))
        else:
            return {'success': False, 'error': 'Missing order_id or external_order_ref'}
        order = request.env['anabtawi.direct.order'].sudo().search(domain, limit=1)
        if not order:
            return {'success': False, 'error': 'Order not found'}
        return {'success': True, 'order_name': order.name, 'state': order.state, 'amount_total': order.amount_total}

class AnabtawiTalabatWebhookController(http.Controller):

    @http.route('/anabtawi/talabat/webhook/<int:config_id>', type='json', auth='public', methods=['POST'], csrf=False)
    def talabat_webhook(self, config_id, **payload):
        config = request.env['anabtawi.talabat.config'].sudo().browse(config_id)
        if not config.exists() or not config.active:
            return {'success': False, 'error': 'Invalid Talabat configuration'}
        secret = request.httprequest.args.get('secret')
        if config.webhook_secret and secret != config.webhook_secret:
            return {'success': False, 'error': 'Invalid webhook secret'}
        data = payload or {}
        try:
            order = config._create_or_update_order_from_payload(data)
            return {'success': True, 'order_id': order.id, 'order_name': order.name, 'state': order.state}
        except Exception as exc:
            request.env['anabtawi.talabat.api.log'].sudo().create({
                'config_id': config.id,
                'method': 'WEBHOOK',
                'endpoint': '/anabtawi/talabat/webhook/%s' % config.id,
                'state': 'failed',
                'request_payload': json.dumps(data, ensure_ascii=False),
                'response_payload': str(exc),
            })
            return {'success': False, 'error': str(exc)}

class AnabtawiOrderingNotificationController(http.Controller):

    @http.route('/anabtawi_ordering/notifications/poll', type='json', auth='user', methods=['POST'], csrf=False)
    def poll_notifications(self, branch_id=None, pos_config_id=None, limit=20, **kwargs):
        """Polling endpoint for POS/browser screens.

        The POS frontend can call this every few seconds and decide which enabled
        actions to execute: popup, sound, print ticket, timer color, notification
        center, or screen-mode display.
        """
        domain = [('state', 'in', ('new', 'shown'))]
        if branch_id:
            domain.append(('branch_id', '=', int(branch_id)))
        if pos_config_id:
            domain.append(('pos_config_id', '=', int(pos_config_id)))
        notifications = request.env['anabtawi.order.notification'].sudo().search(domain, order='priority desc, create_date asc', limit=int(limit or 20))
        result = []
        for n in notifications:
            order = n.order_id
            result.append({
                'id': n.id,
                'name': n.name,
                'event_type': n.event_type,
                'state': n.state,
                'branch_id': n.branch_id.id,
                'branch_name': n.branch_id.name,
                'order_id': order.id if order else False,
                'order_name': order.name if order else False,
                'channel': order.channel if order else False,
                'customer_name': order.customer_name if order else False,
                'customer_phone': order.customer_phone if order else False,
                'amount_total': order.amount_total if order else 0.0,
                'message': n.message,
                'popup_required': n.popup_required,
                'blocking_popup': n.blocking_popup,
                'sound_required': n.sound_required,
                'sound_type': n.sound_type,
                'repeat_until_ack': n.repeat_until_ack,
                'print_required': n.print_required,
                'timer_required': n.timer_required,
                'screen_required': n.screen_required,
                'manager_alert_required': n.manager_alert_required,
                'priority': n.priority,
                'color_status': n.color_status,
            })
        notifications.action_mark_shown()
        return {'count': len(result), 'notifications': result}

    @http.route('/anabtawi_ordering/notifications/ack', type='json', auth='user', methods=['POST'], csrf=False)
    def acknowledge_notifications(self, notification_ids=None, **kwargs):
        ids = [int(x) for x in (notification_ids or [])]
        notifications = request.env['anabtawi.order.notification'].sudo().browse(ids).exists()
        notifications.action_acknowledge()
        return {'ok': True, 'acknowledged': len(notifications)}
