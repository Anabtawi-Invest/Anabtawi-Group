# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LogisticsRequest(models.Model):
    _name = 'logistics.request'
    _description = 'Logistics Quotation Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Request Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
    )
    source_type = fields.Selection(
        [
            ('sale', 'Sales Order'),
            ('purchase', 'Purchase Order'),
        ],
        string='Source Type',
        required=True,
        default='sale',
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    shipping_mode = fields.Selection(
        [
            ('air', 'Air'),
            ('land', 'Land'),
            ('sea', 'Sea'),
        ],
        string='Shipping Mode',
        required=True,
        default='sea',
        tracking=True,
    )
    shipment_type = fields.Selection(
        [
            ('dry', 'Dry'),
            ('cooling', 'Cooling'),
            ('freezer', 'Freezer'),
        ],
        string='Environment',
        required=True,
        default='dry',
        tracking=True,
    )
    container_size = fields.Selection(
        [
            ('20ft', '20ft Container'),
            ('40ft', '40ft Container'),
            ('reefer', 'Reefer Container'),
            ('lcl', 'LCL (Less than Container)'),
            ('pallet', 'Pallet Cargo'),
            ('cbm', 'CBM Volume'),
        ],
        string='Container / Package Size',
        default='40ft',
        tracking=True,
    )
    package_details = fields.Text(
        string='Package & Weight Details',
        help='Weight, dimensions, special handling requirements',
    )
    destination_address = fields.Text(
        string='Destination / Shipping Address',
    )
    line_ids = fields.One2many(
        'logistics.request.line',
        'request_id',
        string='Forwarder Quotations',
        copy=True,
    )
    selected_line_id = fields.Many2one(
        'logistics.request.line',
        string='Selected Quote',
        tracking=True,
        domain="[('request_id', '=', id)]",
    )
    generated_po_id = fields.Many2one(
        'purchase.order',
        string='Logistics PO',
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('rfq', 'RFQs Sent'),
            ('quoted', 'Quotes Received'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    notes = fields.Text(string='Internal Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('logistics.request')
                    or _('New')
                )
        return super().create(vals_list)

    def action_send_rfq(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.state = 'rfq'
            rec.message_post(body=_("RFQs sent to logistics forwarders."))

    def action_quotes_received(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Please add at least one forwarder quotation line before moving to Quotes Received."))
            rec.state = 'quoted'
            rec.message_post(body=_("Forwarder quotes received."))

    def action_confirm_logistics(self):
        for rec in self:
            rec.ensure_one()
            if not rec.selected_line_id:
                raise UserError(_("Please select a winning forwarder quote before confirming."))

            # 1. Fetch or create default freight service product
            freight_product = self.env.ref(
                'logistics_quotation.product_freight_service',
                raise_if_not_found=False,
            )
            if not freight_product:
                freight_product = self.env['product.product'].create({
                    'name': 'Freight & Handling Service',
                    'type': 'service',
                    'list_price': 0.0,
                    'landed_cost_ok': True,
                    'sale_ok': True,
                    'purchase_ok': True,
                })

            selected_line = rec.selected_line_id
            forwarder_partner = selected_line.partner_id
            total_price = selected_line.price_total

            # 2. Create Purchase Order to Freight Forwarder
            po_description = (
                f"Freight Service ({rec.shipping_mode.upper()} - "
                f"{rec.shipment_type.upper()}) - {rec.name}"
            )
            po_vals = {
                'partner_id': forwarder_partner.id,
                'company_id': rec.company_id.id,
                'order_line': [
                    (
                        0,
                        0,
                        {
                            'name': po_description,
                            'product_id': freight_product.id,
                            'product_qty': 1.0,
                            'price_unit': total_price,
                            'date_planned': fields.Datetime.now(),
                        },
                    )
                ],
            }
            logistics_po = self.env['purchase.order'].create(po_vals)
            rec.generated_po_id = logistics_po.id

            # 3. If source is Sales Order, inject freight line into Sales Order
            if rec.source_type == 'sale' and rec.sale_order_id:
                so_description = (
                    f"Shipping & Handling ({rec.shipping_mode.upper()} - "
                    f"{rec.shipment_type.upper()})"
                )
                rec.sale_order_id.write({
                    'order_line': [
                        (
                            0,
                            0,
                            {
                                'product_id': freight_product.id,
                                'name': so_description,
                                'product_uom_qty': 1.0,
                                'price_unit': total_price,
                            },
                        )
                    ]
                })

            rec.state = 'confirmed'
            rec.message_post(
                body=_(
                    "Logistics order confirmed. Purchase Order %s created for forwarder %s.",
                    logistics_po.name,
                    forwarder_partner.display_name,
                )
            )

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_view_po(self):
        self.ensure_one()
        if not self.generated_po_id:
            raise UserError(_("No Purchase Order has been generated yet."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Forwarder PO'),
            'res_model': 'purchase.order',
            'res_id': self.generated_po_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class LogisticsRequestLine(models.Model):
    _name = 'logistics.request.line'
    _description = 'Forwarder Quotation Line'
    _order = 'price_total asc, id asc'

    request_id = fields.Many2one(
        'logistics.request',
        string='Logistics Request',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='request_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Freight Forwarder / Vendor',
        required=True,
        domain="['|', ('supplier_rank', '>', 0), ('is_company', '=', True)]",
    )
    price_subtotal = fields.Monetary(
        string='Freight Cost',
        required=True,
        default=0.0,
    )
    handling_fee = fields.Monetary(
        string='Handling Fee',
        default=0.0,
    )
    price_total = fields.Monetary(
        string='Total Cost',
        compute='_compute_price_total',
        store=True,
    )
    transit_time_days = fields.Integer(
        string='Transit Time (Days)',
    )
    notes = fields.Text(
        string='Conditions / Remarks',
    )

    @api.depends('price_subtotal', 'handling_fee')
    def _compute_price_total(self):
        for line in self:
            line.price_total = (line.price_subtotal or 0.0) + (line.handling_fee or 0.0)
