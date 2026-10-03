# -*- coding: utf-8 -*-
from odoo import api, fields, models, Command, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    logistics_request_ids = fields.One2many(
        'logistics.request',
        'sale_order_id',
        string='Logistics Requests',
    )
    logistics_count = fields.Integer(
        compute='_compute_logistics_count',
        string='Logistics Count',
    )
    show_shipping_request_button = fields.Boolean(
        string='Show Shipping Request Button',
        compute='_compute_show_shipping_request_button',
        store=True,
    )

    @api.depends('logistics_request_ids')
    def _compute_logistics_count(self):
        for order in self:
            order.logistics_count = len(order.logistics_request_ids)

    @api.depends('team_id', 'team_id.use_logistics_shipping_request')
    def _compute_show_shipping_request_button(self):
        for order in self:
            order.show_shipping_request_button = bool(
                order.team_id and order.team_id.use_logistics_shipping_request
            )

    def action_request_shipping_cost(self):
        self.ensure_one()

        # Build packaging breakdown items WITHOUT prices
        item_vals = []
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            weight = (line.product_id.weight or 0.0) * line.product_uom_qty
            volume = (line.product_id.volume or 0.0) * line.product_uom_qty
            uom = getattr(line, 'product_uom_id', False) or getattr(line, 'product_uom', False)
            item_vals.append(
                Command.create({
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.display_name,
                    'quantity': line.product_uom_qty,
                    'product_uom_id': uom.id if uom else False,
                    'weight': weight,
                    'volume': volume,
                })
            )

        destination = ""
        if self.partner_shipping_id:
            destination = self.partner_shipping_id._display_address(without_company=True)
        elif self.partner_id:
            destination = self.partner_id._display_address(without_company=True)

        req_vals = {
            'source_type': 'sale',
            'sale_order_id': self.id,
            'company_id': self.company_id.id,
            'destination_address': destination,
            'item_ids': item_vals,
        }
        logistics_req = self.env['logistics.request'].create(req_vals)

        self.message_post(
            body=_(
                "Logistics Request <b>%s</b> created and routed to Logistics Officer for freight quotation.",
                logistics_req.name,
            )
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Logistics Request Created'),
                'message': _('Logistics Request %s has been submitted to the Logistics Officer.', logistics_req.name),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_open_logistics_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Logistics Requests',
            'res_model': 'logistics.request',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_source_type': 'sale',
                'default_sale_order_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }
