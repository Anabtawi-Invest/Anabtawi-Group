# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PosSelfOrderRequest(models.Model):
    _name = 'pos.self.order.request'
    _description = 'Mobile Self-Order Request'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    pos_order_id = fields.Many2one('pos.order', string='POS Order', required=True, ondelete='cascade', index=True)
    config_id = fields.Many2one('pos.config', string='Point of Sale', required=True, index=True)
    session_id = fields.Many2one('pos.session', string='POS Session', index=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='pos_order_id.partner_id', store=True)
    source = fields.Selection(
        selection=[('mobile', 'Self-Order Mobile')],
        string='Source',
        required=True,
        default='mobile',
    )
    customer_latitude = fields.Float(string='Latitude', digits=(10, 7))
    customer_longitude = fields.Float(string='Longitude', digits=(10, 7))
    location_url = fields.Char(string='Map Link', compute='_compute_location_url')
    line_summary = fields.Text(string='Order Lines', compute='_compute_line_summary')
    amount_total = fields.Monetary(string='Total', related='pos_order_id.amount_total')
    currency_id = fields.Many2one('res.currency', related='pos_order_id.currency_id')
    pos_order_state = fields.Selection(related='pos_order_id.state', string='POS Order State')
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('accepted', 'Accepted'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='new',
        required=True,
        index=True,
    )

    @api.depends('customer_latitude', 'customer_longitude')
    def _compute_location_url(self):
        for record in self:
            if record.customer_latitude and record.customer_longitude:
                record.location_url = (
                    f'https://maps.google.com/?q={record.customer_latitude},{record.customer_longitude}'
                )
            else:
                record.location_url = False

    @api.depends('pos_order_id', 'pos_order_id.lines', 'pos_order_id.lines.product_id')
    def _compute_line_summary(self):
        for record in self:
            if not record.pos_order_id:
                record.line_summary = False
                continue
            record.line_summary = '\n'.join(
                f'{line.qty:g} x {line.full_product_name or line.product_id.display_name}'
                for line in record.pos_order_id.lines
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pos.self.order.request') or _('New')
        return super().create(vals_list)

    @api.model
    def _sync_from_pos_order(self, order):
        """Create or update a request record from a mobile self-order."""
        order.ensure_one()
        if order.source != 'mobile':
            return self.env['pos.self.order.request']

        vals = {
            'customer_latitude': order.customer_latitude,
            'customer_longitude': order.customer_longitude,
            'config_id': order.config_id.id,
            'session_id': order.session_id.id,
        }

        if order.state == 'paid':
            vals['state'] = 'done'
        elif order.state == 'cancel':
            vals['state'] = 'cancelled'

        request = order.self_order_request_id
        if request:
            request.write(vals)
            return request

        request = self.create({
            **vals,
            'pos_order_id': order.id,
            'source': 'mobile',
        })
        order.sudo().write({'self_order_request_id': request.id})
        return request

    @api.model
    def get_open_requests(self, config_id):
        """Return open mobile self-order requests for the POS UI popup."""
        requests = self.search([
            ('config_id', '=', config_id),
            ('state', 'in', ['new', 'accepted']),
        ])
        return [{
            'id': request.id,
            'name': request.name,
            'state': request.state,
            'amount_total': request.amount_total,
            'currency_id': request.currency_id.id,
            'line_summary': request.line_summary or '',
            'customer_latitude': request.customer_latitude,
            'customer_longitude': request.customer_longitude,
            'location_url': request.location_url,
            'pos_order_id': request.pos_order_id.id,
            'pos_reference': request.pos_order_id.pos_reference,
            'tracking_number': request.pos_order_id.tracking_number,
            'create_date': fields.Datetime.to_string(request.create_date),
        } for request in requests]

    def action_mark_accepted(self):
        self.filtered(lambda r: r.state == 'new').write({'state': 'accepted'})

    def action_mark_done(self):
        self.filtered(lambda r: r.state in ('new', 'accepted')).write({'state': 'done'})

    def action_mark_cancelled(self):
        self.write({'state': 'cancelled'})

    def action_open_map(self):
        self.ensure_one()
        if not self.location_url:
            return False
        return {
            'type': 'ir.actions.act_url',
            'url': self.location_url,
            'target': 'new',
        }

    def action_open_pos_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('POS Order'),
            'res_model': 'pos.order',
            'view_mode': 'form',
            'res_id': self.pos_order_id.id,
            'target': 'current',
        }
