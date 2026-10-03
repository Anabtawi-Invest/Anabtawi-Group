# -*- coding: utf-8 -*-
import uuid
from odoo import _, api, fields, models, Command
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
            ('sale', 'Sales Order (Outbound Export)'),
            ('purchase', 'Purchase Order (Inbound Import)'),
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
    incoterm_id = fields.Many2one(
        'account.incoterms',
        string='Incoterm',
        help='International Commercial Terms (e.g. FOB, CIF, DDP, EXW)',
        tracking=True,
    )
    shipping_mode = fields.Selection(
        [
            ('air', 'Air Freight'),
            ('land', 'Land Transport'),
            ('sea', 'Sea Freight'),
        ],
        string='Shipping Mode',
        required=True,
        default='sea',
        tracking=True,
    )
    shipment_type = fields.Selection(
        [
            ('dry', 'Dry / Ambient'),
            ('cooling', 'Chilled / Cooling (Chocolates & Confectionery)'),
            ('freezer', 'Frozen (-18°C)'),
        ],
        string='Environment Control',
        required=True,
        default='dry',
        tracking=True,
    )
    container_size = fields.Selection(
        [
            ('20ft', '20ft Dry Container'),
            ('40ft', '40ft Dry Container'),
            ('20ft_reefer', '20ft Reefer Container'),
            ('40ft_reefer', '40ft Reefer Container'),
            ('lcl', 'LCL (Less than Container Load)'),
            ('pallet', 'Palletised Truck Cargo'),
            ('cbm', 'CBM Volume Cargo'),
        ],
        string='Container / Equipment Spec',
        default='40ft',
        tracking=True,
    )
    cargo_insurance_required = fields.Boolean(
        string='Cargo Insurance Required',
        default=False,
        help='Check if marine/transit cargo insurance quotation is required from forwarder',
    )
    is_hazardous = fields.Boolean(
        string='Hazardous / Dangerous Goods (DG)',
        default=False,
        help='Check if cargo contains hazardous materials requiring MSDS',
    )
    temperature_control_notes = fields.Char(
        string='Temperature Target / Specs',
        placeholder='e.g., +15°C to +18°C constant temperature',
    )
    package_details = fields.Text(
        string='Package & Cargo Summary',
        help='Dimensions, total packages, gross weight, CBM volume, and special handling instructions',
    )
    destination_address = fields.Text(
        string='Destination / Shipping Address',
    )
    item_ids = fields.One2many(
        'logistics.request.item',
        'request_id',
        string='Packaging & Cargo Breakdown',
        copy=True,
    )
    total_weight = fields.Float(
        string='Total Weight (kg)',
        compute='_compute_totals',
        store=True,
    )
    total_volume = fields.Float(
        string='Total Volume (m³ / CBM)',
        compute='_compute_totals',
        store=True,
    )
    invitation_ids = fields.One2many(
        'logistics.request.invitation',
        'request_id',
        string='Forwarder Response Tracker',
        copy=False,
    )
    invitation_count = fields.Integer(
        compute='_compute_invitation_stats',
        string='Total Forwarders Invited',
    )
    submitted_count = fields.Integer(
        compute='_compute_invitation_stats',
        string='Responded Forwarders',
    )
    line_ids = fields.One2many(
        'logistics.request.line',
        'request_id',
        string='Forwarder Quotations',
        copy=True,
    )
    selected_line_id = fields.Many2one(
        'logistics.request.line',
        string='Selected Winning Quote',
        tracking=True,
        domain="[('request_id', '=', id)]",
    )
    generated_po_id = fields.Many2one(
        'purchase.order',
        string='Forwarder PO',
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('rfq', 'RFQs Broadcasted'),
            ('quoted', 'Quotes Received'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    
    # Financial Approval Guardrails
    requires_approval = fields.Boolean(
        string='Requires Manager Approval',
        compute='_compute_requires_approval',
        store=True,
    )
    approval_state = fields.Selection(
        [
            ('none', 'Not Required'),
            ('pending', 'Pending Manager Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Financial Approval Status',
        default='none',
        tracking=True,
    )
    
    # Shipment Milestone Tracking (Post-Award Execution)
    bl_awb_number = fields.Char(
        string='Bill of Lading / Air Waybill #',
        tracking=True,
        help='Master BL or AWB tracking number provided by carrier/forwarder',
    )
    container_number = fields.Char(
        string='Container / Truck Number',
        tracking=True,
    )
    vessel_flight_name = fields.Char(
        string='Vessel / Flight Name',
        tracking=True,
    )
    etd_date = fields.Date(
        string='Estimated Time of Departure (ETD)',
        tracking=True,
    )
    eta_date = fields.Date(
        string='Estimated Time of Arrival (ETA)',
        tracking=True,
    )
    notes = fields.Text(string='Internal Notes')

    @api.depends('item_ids.weight', 'item_ids.volume', 'item_ids.quantity')
    def _compute_totals(self):
        for rec in self:
            rec.total_weight = sum(rec.item_ids.mapped('weight'))
            rec.total_volume = sum(rec.item_ids.mapped('volume'))

    @api.depends('invitation_ids', 'invitation_ids.state')
    def _compute_invitation_stats(self):
        for rec in self:
            rec.invitation_count = len(rec.invitation_ids)
            rec.submitted_count = len(rec.invitation_ids.filtered(lambda i: i.state == 'submitted'))

    @api.depends('selected_line_id', 'selected_line_id.price_total')
    def _compute_requires_approval(self):
        # High-cost freight threshold guardrail (e.g. > 5000)
        THRESHOLD = 5000.0
        for rec in self:
            if rec.selected_line_id and rec.selected_line_id.price_total > THRESHOLD:
                rec.requires_approval = True
                if rec.approval_state == 'none':
                    rec.approval_state = 'pending'
            else:
                rec.requires_approval = False
                if rec.approval_state == 'pending':
                    rec.approval_state = 'none'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('logistics.request')
                    or _('New')
                )
        return super().create(vals_list)

    def action_broadcast_rfq(self):
        """Broadcast RFQs in 1 click to all Accounting-Approved Freight Forwarders."""
        for rec in self:
            rec.ensure_one()
            approved_forwarders = self.env['res.partner'].search([
                ('is_freight_forwarder', '=', True),
                ('forwarder_approval_state', '=', 'approved'),
            ])
            if not approved_forwarders:
                raise UserError(_("No Accounting-Approved Freight Forwarders found! Please ensure forwarders are verified by Accounting Manager."))

            template = self.env.ref('logistics_quotation.email_template_logistics_rfq', raise_if_not_found=False)
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

            broadcast_count = 0
            for partner in approved_forwarders:
                invitation = rec.invitation_ids.filtered(lambda i: i.partner_id.id == partner.id)
                if not invitation:
                    invitation = self.env['logistics.request.invitation'].create({
                        'request_id': rec.id,
                        'partner_id': partner.id,
                    })

                token_url = f"{base_url}/logistics/rfq/submit/{invitation.token}"
                
                if template and partner.email:
                    template.with_context(
                        custom_token_url=token_url,
                        email_to=partner.email,
                    ).send_mail(rec.id, force_send=True)
                    broadcast_count += 1

            rec.state = 'rfq'
            rec.message_post(
                body=_(
                    "RFQ broadcasted to %s Accounting-Approved Freight Forwarder(s) via secure web upload links.",
                    broadcast_count or len(approved_forwarders),
                )
            )

    def get_portal_url(self, partner_id=None):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        invitation = False
        if partner_id:
            invitation = self.invitation_ids.filtered(lambda i: i.partner_id.id == partner_id)
        if not invitation and self.invitation_ids:
            invitation = self.invitation_ids[0]
        if not invitation:
            approved_forwarder = self.env['res.partner'].search([
                ('is_freight_forwarder', '=', True),
                ('forwarder_approval_state', '=', 'approved'),
            ], limit=1)
            if approved_forwarder:
                invitation = self.env['logistics.request.invitation'].create({
                    'request_id': self.id,
                    'partner_id': approved_forwarder.id,
                })
        if invitation:
            return f"{base_url}/logistics/rfq/submit/{invitation.token}"
        return f"{base_url}/web"

    def action_send_rfq_email(self):
        self.ensure_one()
        template = self.env.ref(
            'logistics_quotation.email_template_logistics_rfq',
            raise_if_not_found=False,
        )
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', raise_if_not_found=False)

        if self.state == 'draft':
            self.state = 'rfq'

        token_url = self.get_portal_url()

        ctx = {
            'default_model': 'logistics.request',
            'default_res_ids': [self.id],
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'custom_token_url': token_url,
            'force_email': True,
        }
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id if compose_form else False, 'form')],
            'view_id': compose_form.id if compose_form else False,
            'target': 'new',
            'context': ctx,
        }

    def action_print_rfq(self):
        self.ensure_one()
        return self.env.ref('logistics_quotation.action_report_logistics_request').report_action(self)

    def action_approve_logistics(self):
        """Manager Approval action for high-cost freight orders."""
        for rec in self:
            rec.approval_state = 'approved'
            rec.message_post(body=_("Logistics quotation approved by Manager %s.", self.env.user.name))

    def action_reject_logistics(self):
        """Manager Rejection action."""
        for rec in self:
            rec.approval_state = 'rejected'
            rec.message_post(body=_("Logistics quotation rejected by Manager %s.", self.env.user.name))

    def action_confirm_logistics(self):
        for rec in self:
            rec.ensure_one()
            if not rec.selected_line_id:
                raise UserError(_("Please select a winning forwarder quote before confirming."))

            if rec.requires_approval and rec.approval_state != 'approved':
                raise UserError(_("This logistics request requires Manager Approval before confirmation because total freight cost exceeds threshold."))

            # Fetch or create default freight service product
            freight_product = self.env.ref(
                'logistics_quotation.product_freight_service',
                raise_if_not_found=False,
            )
            if not freight_product:
                freight_product = self.env['product.product'].create({
                    'name': 'Freight & Shipping Service',
                    'type': 'service',
                    'list_price': 0.0,
                    'landed_cost_ok': True,
                    'sale_ok': True,
                    'purchase_ok': True,
                })

            selected_line = rec.selected_line_id
            forwarder_partner = selected_line.partner_id
            total_price = selected_line.price_total

            # 1. Create Purchase Order for Freight Forwarder
            po_description = (
                f"Freight Shipping Service ({rec.shipping_mode.upper()} - "
                f"{rec.shipment_type.upper()}) - Request: {rec.name}"
            )
            if selected_line.free_days_port:
                po_description += f" ({selected_line.free_days_port} Port Free Days Included)"

            po_vals = {
                'partner_id': forwarder_partner.id,
                'company_id': rec.company_id.id,
                'order_line': [
                    Command.create({
                        'name': po_description,
                        'product_id': freight_product.id,
                        'product_qty': 1.0,
                        'price_unit': total_price,
                        'date_planned': fields.Datetime.now(),
                    })
                ],
            }
            logistics_po = self.env['purchase.order'].create(po_vals)
            rec.generated_po_id = logistics_po.id

            # 2. If source is Sales Order, inject freight cost line into Sales Order
            if rec.source_type == 'sale' and rec.sale_order_id:
                so_description = (
                    f"International Shipping & Freight ({rec.shipping_mode.upper()} - "
                    f"{rec.shipment_type.upper()})"
                )
                rec.sale_order_id.write({
                    'order_line': [
                        Command.create({
                            'product_id': freight_product.id,
                            'name': so_description,
                            'product_uom_qty': 1.0,
                            'price_unit': total_price,
                        })
                    ]
                })

            rec.state = 'confirmed'
            rec.message_post(
                body=_(
                    "Logistics order confirmed successfully. Forwarder Purchase Order %s created for %s (Total: %s).",
                    logistics_po.name,
                    forwarder_partner.display_name,
                    total_price,
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


class LogisticsRequestItem(models.Model):
    _name = 'logistics.request.item'
    _description = 'Logistics Cargo Item (Price Confidential)'

    request_id = fields.Many2one(
        'logistics.request',
        string='Logistics Request',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
    )
    name = fields.Char(
        string='Description / Packaging Specification',
        required=True,
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
    )
    weight = fields.Float(
        string='Gross Weight (kg)',
        help='Gross weight for this cargo item line',
    )
    volume = fields.Float(
        string='Volume (m³ / CBM)',
        help='Volume for this cargo item line',
    )


class LogisticsRequestInvitation(models.Model):
    _name = 'logistics.request.invitation'
    _description = 'Forwarder Response & Invitation Tracker'
    _rec_name = 'partner_id'
    _order = 'submitted_date desc, id desc'

    request_id = fields.Many2one(
        'logistics.request',
        string='Logistics Request',
        required=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Forwarder Partner',
        required=True,
    )
    email = fields.Char(
        related='partner_id.email',
        string='Forwarder Email',
        readonly=True,
    )
    token = fields.Char(
        string='Secure Access Token',
        required=True,
        default=lambda self: uuid.uuid4().hex,
        copy=False,
    )
    state = fields.Selection(
        [
            ('pending', 'Pending Response'),
            ('submitted', 'Submitted'),
            ('declined', 'Declined'),
        ],
        string='Response Status',
        default='pending',
        required=True,
    )
    submitted_date = fields.Datetime(
        string='Submission Date',
        readonly=True,
    )
    quote_line_id = fields.Many2one(
        'logistics.request.line',
        string='Submitted Quotation Line',
        readonly=True,
    )


class LogisticsRequestLine(models.Model):
    _name = 'logistics.request.line'
    _description = 'Forwarder Quotation Line'
    _rec_name = 'partner_id'
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
    origin_handling_fee = fields.Monetary(
        string='Origin Handling Fee',
        default=0.0,
        help='Handling and export documentation fees in origin country',
    )
    freight_cost = fields.Monetary(
        string='Main Freight Shipping Cost',
        default=0.0,
        help='Main ocean, air, or land shipping transport cost',
    )
    destination_handling_fee = fields.Monetary(
        string='Destination Handling Fee',
        default=0.0,
        help='Terminal handling (THC), port, and unloading fees in receiving country',
    )
    customs_clearance_fee = fields.Monetary(
        string='Customs Clearance Fees',
        default=0.0,
        help='Customs clearance, brokerage, and documentation fees at destination',
    )
    price_total = fields.Monetary(
        string='Total Cost',
        compute='_compute_price_total',
        store=True,
    )
    transit_time_days = fields.Integer(
        string='Transit Time (Days)',
    )
    free_days_port = fields.Integer(
        string='Free Demurrage Days (Port)',
        default=14,
        help='Number of free demurrage/detention storage days granted at destination port',
    )
    quote_attachment = fields.Binary(
        string='Quote PDF / Document',
        attachment=True,
        help='Uploaded PDF or scanned document from freight forwarder',
    )
    quote_filename = fields.Char(
        string='File Name',
    )
    notes = fields.Text(
        string='Conditions & Remarks',
    )

    @api.depends('origin_handling_fee', 'freight_cost', 'destination_handling_fee', 'customs_clearance_fee')
    def _compute_price_total(self):
        for line in self:
            line.price_total = (
                (line.origin_handling_fee or 0.0) +
                (line.freight_cost or 0.0) +
                (line.destination_handling_fee or 0.0) +
                (line.customs_clearance_fee or 0.0)
            )

    @api.depends('partner_id.name', 'price_total', 'currency_id.symbol')
    def _compute_display_name(self):
        for line in self:
            partner_name = line.partner_id.name or _('Forwarder')
            currency = line.currency_id.symbol or ''
            line.display_name = f"{partner_name} - {line.price_total} {currency}".strip()
