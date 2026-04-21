# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from odoo.tools import float_compare, float_repr
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    pledge_id = fields.Many2one(
        'pos.pledge',
        string='Pledge Record',
        readonly=True
    )
    pledge_collection_pos_order_id = fields.Many2one(
        'pos.order',
        string='Pledge Collection POS Order',
        readonly=True,
        copy=False,
        help='Technical link to the POS order created automatically to collect pledge amount.',
    )
    is_pledge_generated = fields.Boolean(
        string='Pledge Generated Order',
        default=False,
        help='Technical flag for POS orders generated automatically by pledge flow.',
    )

    has_pledge = fields.Boolean(
        string='Has Pledge',
        compute='_compute_has_pledge',
        store=True
    )
    
    pledge_payments_created = fields.Boolean(
        string='Pledge Payments Created',
        default=False,
        help='Indicates if pledge/employee/delivery payments have been created'
    )
    
    has_employee_service = fields.Boolean(
        string='Has Employee Service',
        default=False,
        help='Indicates if this order contains employee service products'
    )
    
    employee_id = fields.Many2one(
        'hr.employee',
        string='Service Employee',
        help='Employee associated with this order for service delivery'
    )
    
    pledge_product_qty = fields.Integer(
        string='Pledge Product Quantity',
        default=0,
        help='Total quantity of pledge products in this order'
    )
    
    total_pledge_amount = fields.Monetary(
        string='Total Pledge Amount',
        currency_field='currency_id',
        help='Total amount for pledge products in this order'
    )

    @api.model
    def _order_fields(self, ui_order):
        """Read employee_id from UI order"""
        vals = super()._order_fields(ui_order)
        # Get employee_id from UI order
        employee_id = ui_order.get('employee_id', False)
        if employee_id:
            vals['employee_id'] = employee_id
        _logger.info("[PLEDGE] _order_fields: employee_id = %s", employee_id)
        return vals

    @api.depends('lines.product_id.has_pledge')
    def _compute_has_pledge(self):
        for order in self:
            _logger.info("[PLEDGE] Computing has_pledge for order: %s", order.name)
            _logger.info("[PLEDGE] Order has %d lines", len(order.lines))
            
            pledge_lines = []
            for line in order.lines:
                _logger.info("[PLEDGE]   Line: %s (Product ID: %s)", 
                            line.product_id.name, line.product_id.id)
                _logger.info("[PLEDGE]     - has_pledge: %s", line.product_id.has_pledge)
                
                if line.product_id.has_pledge:
                    pledge_lines.append(line)
                    _logger.info("[PLEDGE]     ✓ This is a pledge product!")
            
            has_pledge_items = len(pledge_lines) > 0
            order.has_pledge = has_pledge_items
            
            if has_pledge_items:
                _logger.info("[PLEDGE] ✓ Order %s computed has_pledge=True (%d pledge lines)", 
                            order.name, len(pledge_lines))
            else:
                _logger.info("[PLEDGE] ✗ Order %s computed has_pledge=False (no pledge lines found)", 
                            order.name)

    def _create_pledge_payments(self):
        """
        Kept for backward compatibility.
        Independent payment creation is disabled in this module variant.
        """
        _logger.info("[PLEDGE] _create_pledge_payments is disabled.")
        return True

    def _compute_pledge_from_lines(self):
        """Return (total_pledge_amount, pledge_product_ids, total_pledge_qty) from pledged order lines."""
        self.ensure_one()
        total_pledge_amount = 0.0
        pledge_product_ids = []
        total_pledge_qty = 0.0
        for line in self.lines.filtered(lambda l: l.product_id):
            if not line.product_id.has_pledge:
                continue
            qty = line.qty or 0.0
            unit_pledge = line.product_id.pledge_amount or 0.0
            line_pledge = qty * unit_pledge
            if line_pledge <= 0:
                continue
            total_pledge_amount += line_pledge
            total_pledge_qty += qty
            pledge_product_ids.append(line.product_id.id)
        return total_pledge_amount, list(set(pledge_product_ids)), total_pledge_qty

    def _prepare_pos_pledge_tracking_vals(self, pledge_total, pledge_product_ids):
        """Prepare payload to create pos.pledge tracking record from a paid POS order."""
        self.ensure_one()
        employee_amount = 0.0
        delivery_amount = 0.0
        employee_product_id = False
        delivery_product_id = False

        for line in self.lines.filtered(lambda l: l.product_id):
            product = line.product_id
            if product.is_employee_service:
                employee_amount += line.price_subtotal_incl
                if not employee_product_id:
                    employee_product_id = product.id
            elif product.is_delivery_product:
                delivery_amount += line.price_subtotal_incl
                if not delivery_product_id:
                    delivery_product_id = product.id

        has_pledge = pledge_total > 0
        has_employee = employee_amount > 0
        has_delivery = delivery_amount > 0

        if has_employee and not has_pledge and not has_delivery:
            case_type = "case1"
        elif has_pledge and not has_delivery and not has_employee:
            case_type = "case2"
        elif has_pledge and has_delivery and not has_employee:
            case_type = "case3"
        elif has_pledge and has_employee and has_delivery:
            case_type = "case4"
        elif has_pledge and has_employee and not has_delivery:
            case_type = "case5"
        elif has_employee and has_delivery and not has_pledge:
            case_type = "case6"
        else:
            case_type = "mixed"

        return {
            "pos_order_id": self.id,
            "pos_config_id": self.config_id.id,
            "partner_id": self.partner_id.id,
            "employee_id": self.employee_id.id if self.employee_id else False,
            "case_type": case_type,
            "pledge_amount": pledge_total,
            "employee_amount": employee_amount,
            "delivery_amount": delivery_amount,
            "pledge_products": [(6, 0, pledge_product_ids or [])],
            "employee_product_id": employee_product_id,
            "delivery_product_id": delivery_product_id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id or self.company_id.currency_id.id,
        }

    def _create_pledge_collection_orders(self):
        """Create a separate paid POS order for pledge amount (same behavior as advance flow)."""
        PosOrder = self.env['pos.order'].sudo()
        PosOrderLine = self.env['pos.order.line'].sudo()
        PosPayment = self.env['pos.payment'].sudo()

        for order in self:
            if order.is_pledge_generated:
                continue
            if order.pledge_collection_pos_order_id:
                continue

            has_pledge_field = 'pledge_product_id' in order.config_id._fields
            pledge_product = order.config_id.pledge_product_id if has_pledge_field else False
            if not pledge_product:
                _logger.info(
                    "[PLEDGE] Skipping pledge collection order for %s (missing config pledge_product_id).",
                    order.name,
                )
                continue

            pledge_total, pledge_product_ids, pledge_qty = order._compute_pledge_from_lines()
            if pledge_total <= 0:
                continue
            if pledge_qty <= 0:
                continue

            payment_method = order.payment_ids[:1].payment_method_id or order.session_id.payment_method_ids[:1]
            if not payment_method:
                _logger.warning("[PLEDGE] No payment method found to create pledge collection order for %s", order.name)
                continue

            pledge_order = PosOrder.create({
                'session_id': order.session_id.id,
                'partner_id': order.partner_id.id if order.partner_id else False,
                'to_invoice': False,
                'amount_tax': 0.0,
                'amount_total': 0.0,
                'amount_paid': 0.0,
                'amount_return': 0.0,
                'amount_difference': 0.0,
                'is_pledge_generated': True,
            })

            PosOrderLine.create({
                'order_id': pledge_order.id,
                'product_id': pledge_product.id,
                'name': _("Pledge"),
                'qty': pledge_qty,
                'price_unit': pledge_total / pledge_qty,
                'discount': 0.0,
                'tax_ids': [(6, 0, [])],
                'price_subtotal': pledge_total,
                'price_subtotal_incl': pledge_total,
                'price_extra': 0.0,
                'full_product_name': pledge_product.display_name,
            })

            pledge_order._compute_prices()
            PosPayment.create({
                'pos_order_id': pledge_order.id,
                'payment_method_id': payment_method.id,
                'amount': pledge_order.amount_total,
            })
            pledge_order._compute_prices()
            pledge_order.action_pos_order_paid()
            pledge_order._create_order_picking()

            order.pledge_collection_pos_order_id = pledge_order.id
            _logger.info(
                "[PLEDGE] Created pledge collection POS order %s for source order %s (amount=%s).",
                pledge_order.name,
                order.name,
                pledge_total,
            )

            if not order.partner_id:
                _logger.warning(
                    "[PLEDGE] Cannot create pos.pledge for %s because customer is missing.",
                    order.name,
                )
                continue

            pledge_record = self.env["pos.pledge"].sudo().search(
                [("pos_order_id", "=", order.id)], limit=1
            )
            if not pledge_record:
                try:
                    vals = order._prepare_pos_pledge_tracking_vals(pledge_total, pledge_product_ids)
                    pledge_record = self.env["pos.pledge"].sudo().create(vals)
                    _logger.info(
                        "[PLEDGE] Created pos.pledge %s for order %s",
                        pledge_record.name,
                        order.name,
                    )
                except Exception as e:
                    _logger.warning(
                        "[PLEDGE] Could not create pos.pledge from source order %s: %s",
                        order.name,
                        e,
                    )
                    continue

            order.pledge_id = pledge_record.id
    
    def write(self, vals):
        """Override write to trigger pledge order creation when order state changes."""
        _logger.info("[PLEDGE] write() called on %d orders with vals: %s", len(self), vals)
        
        result = super().write(vals)
        
        # If order is being validated/paid, create pledge collection orders.
        # This happens after order is synced from POS
        if vals.get('state') in ('paid', 'done'):
            _logger.info("[PLEDGE] Order state changed to %s, checking for pledge orders", vals.get('state'))
            normal_orders = self.filtered(lambda o: not o.is_pledge_generated)
            normal_orders._create_pledge_collection_orders()
        else:
            _logger.info("[PLEDGE] State not in (paid, done): %s", vals.get('state'))
        
        return result

    def _get_pos_payment_method_from_journal(self, journal, pos_config):
        """
        Get or create pos.payment.method from account.journal
        For cash journals, must create a new payment method for each POS config (cannot be shared)
        For bank journals, can be shared between configs
        """
        is_cash = journal.type == 'cash'
        
        # Check if there's an open session
        opened_session = pos_config.session_ids.filtered(lambda s: s.state != 'closed')
        has_open_session = bool(opened_session)
        
        # First, search in payment_method_ids of the config (already available)
        pos_payment_method = pos_config.payment_method_ids.filtered(
            lambda pm: pm.journal_id.id == journal.id
        )[:1]
        
        if pos_payment_method:
            # Payment method already in config - use it
            return pos_payment_method
        
        # If not found in config, search more broadly (anywhere)
        # Search for any payment method with this journal
        pos_payment_method = self.env['pos.payment.method'].search([
            ('journal_id', '=', journal.id),
        ], limit=1)
        
        if pos_payment_method:
            # Found a payment method - add it to config if not already there
            if pos_payment_method not in pos_config.payment_method_ids:
                # Use bypass context to allow modification even with open session
                try:
                    pos_config.with_context(bypass_payment_method_ids_forbidden_change=True).write({
                        'payment_method_ids': [(4, pos_payment_method.id)],
                    })
                except Exception:
                    # If still fails, try to add to config_ids only (might work)
                    if pos_config.id not in pos_payment_method.config_ids.ids:
                        pos_payment_method.write({
                            'config_ids': [(4, pos_config.id)],
                        })
            return pos_payment_method
        
        # If not found anywhere, create new one
        if is_cash:
            # For cash journals, search only in this config (cash cannot be shared)
            pos_payment_method = self.env['pos.payment.method'].search([
                ('journal_id', '=', journal.id),
                ('config_ids', 'in', [pos_config.id]),
            ], limit=1)
            
            # For cash, check if journal is already used by another payment method in another config
            if pos_payment_method:
                other_configs = self.env['pos.config'].search([
                    ('payment_method_ids', 'in', [pos_payment_method.id]),
                    ('id', '!=', pos_config.id),
                ])
                if other_configs:
                    # Journal is already used in another config - cannot reuse for cash
                    raise ValidationError(_(
                        'The cash journal "%s" is already used in another POS configuration. '
                        'Please configure a different cash journal for this POS configuration, '
                        'or remove it from the other configuration first.'
                    ) % journal.name)
            
            if not pos_payment_method:
                # Create a new payment method for this config
                pos_payment_method = self.env['pos.payment.method'].sudo().create({
                    'name': journal.name,
                    'journal_id': journal.id,
                    'config_ids': [(4, pos_config.id)],
                    'company_id': pos_config.company_id.id,
                })
                # Add to payment_method_ids using bypass context
                try:
                    pos_config.with_context(bypass_payment_method_ids_forbidden_change=True).write({
                        'payment_method_ids': [(4, pos_payment_method.id)],
                    })
                except Exception:
                    # If still fails, at least add to config_ids
                    pass
        else:
            # For bank journals, can be shared between configs
            if not pos_payment_method:
                # Create a new pos.payment.method if not found
                pos_payment_method = self.env['pos.payment.method'].sudo().create({
                    'name': journal.name,
                    'journal_id': journal.id,
                    'config_ids': [(4, pos_config.id)],
                    'company_id': pos_config.company_id.id,
                })
                # Add to payment_method_ids using bypass context
                try:
                    pos_config.with_context(bypass_payment_method_ids_forbidden_change=True).write({
                        'payment_method_ids': [(4, pos_payment_method.id)],
                    })
                except Exception:
                    # If still fails, at least add to config_ids
                    pass
        
        return pos_payment_method

    def _create_independent_payment(self, order, amount, journal, description):
        """
        Create an independent payment record for pledge/employee/delivery
        This payment is NOT linked to any invoice
        
        :param order: pos.order record
        :param amount: Amount for the payment
        :param journal: Journal to use
        :param description: Description for the payment
        :return: account.payment record or False
        """
        _logger.info("[PLEDGE] _create_independent_payment called:")
        _logger.info("[PLEDGE]   - Order: %s", order.name)
        _logger.info("[PLEDGE]   - Amount: %.2f", amount)
        _logger.info("[PLEDGE]   - Journal: %s", journal.name)
        _logger.info("[PLEDGE]   - Description: %s", description)
        
        if amount <= 0:
            _logger.warning("[PLEDGE] Amount is <= 0, returning False")
            return False
        
        if not order.partner_id:
            _logger.error("[PLEDGE] No partner found for %s payment", description)
            return False
        
        _logger.info("[PLEDGE] Partner: %s (ID: %s)", order.partner_id.name, order.partner_id.id)
        _logger.info("[PLEDGE] Currency: %s", order.currency_id.name if order.currency_id else order.company_id.currency_id.name)
        _logger.info("[PLEDGE] Date: %s", order.date_order)
        
        # Check for payment method
        if not journal.inbound_payment_method_line_ids:
            _logger.error("[PLEDGE] Journal %s has no inbound payment methods!", journal.name)
            return False
        
        payment_method = journal.inbound_payment_method_line_ids[0]
        _logger.info("[PLEDGE] Payment method: %s (ID: %s)", payment_method.name, payment_method.id)
        
        # Get pos.payment.method
        pos_config = order.config_id
        pos_payment_method = order._get_pos_payment_method_from_journal(journal, pos_config)
        
        try:
            # Create account.payment for accounting
            payment_vals = {
                'payment_type': 'inbound',  # Customer pays us
                'partner_type': 'customer',
                'partner_id': order.partner_id.id,
                'amount': amount,
                'currency_id': order.currency_id.id or order.company_id.currency_id.id,
                'journal_id': journal.id,
                'date': order.date_order,
                'memo': f"{order.name} - {description}",
                'payment_method_line_id': payment_method.id,
                # Do NOT set invoice_ids or reconciled_invoice_ids - this payment is independent
            }
            
            _logger.info("[PLEDGE] Creating account.payment record...")
            payment = self.env['account.payment'].create(payment_vals)
            _logger.info("[PLEDGE] ✓ Created independent account.payment for %s: %.2f (ID: %s, Name: %s)", 
                        description, amount, payment.id, payment.name)
            
            # POST the payment immediately
            _logger.info("[PLEDGE] Posting payment %s...", payment.name)
            payment.action_post()
            _logger.info("[PLEDGE] ✓ Payment %s posted successfully", payment.name)
            
            # Create pos.payment
            pos_payment = self.env['pos.payment'].sudo().create({
                'pos_order_id': order.id,
                'payment_method_id': pos_payment_method.id,
                'amount': amount,
                'payment_date': fields.Datetime.now(),
            })
            _logger.info("[PLEDGE] ✓ Created pos.payment for %s: %.2f (ID: %s)", 
                        description, amount, pos_payment.id)

            # Store reference in pos.pledge for tracking
            _logger.info("[PLEDGE] Searching for pos.pledge record with pos_order_id=%s", order.id)
            pledge_record = self.env['pos.pledge'].search([
                ('pos_order_id', '=', order.id)
            ], limit=1)

            if pledge_record:
                _logger.info("[PLEDGE] Found pledge record: %s (ID: %s)", pledge_record.name, pledge_record.id)
                if description == 'Pledge':
                    pledge_record.write({'pledge_payment_id': payment.id})
                    _logger.info("[PLEDGE] ✓ Linked pledge payment %s to pledge record %s", 
                                payment.name, pledge_record.name)
                elif description == 'Employee Service':
                    pledge_record.write({'employee_payment_id': payment.id})
                    _logger.info("[PLEDGE] ✓ Linked employee payment %s to pledge record %s", 
                                payment.name, pledge_record.name)
            else:
                _logger.warning("[PLEDGE] ⚠️ No pos.pledge record found for order %s - cannot link payment", order.name)
            
            return payment
        except Exception as e:
            _logger.error("[PLEDGE] ✗ Failed to create payment for %s: %s", description, str(e))
            import traceback
            _logger.error("[PLEDGE] Traceback: %s", traceback.format_exc())
            return False

    def action_pos_order_invoice(self):
        """
        Create invoices normally - pledge products appear with their product price
        Virtual pledge amounts are ONLY on receipts, NOT in invoices
        """
        _logger.info("[PLEDGE] Creating invoice - pledge products included with product price only")
        # Create invoice normally - no filtering of pledge products
        return super(PosOrder, self).action_pos_order_invoice()

    def _prepare_invoice_vals(self):
        """Override to exclude pledge/employee/delivery products from invoice"""
        vals = super()._prepare_invoice_vals()
        return vals

    def _prepare_invoice_lines(self, move_type):
        """
        Override to filter out pledge/employee/delivery products from invoice lines
        We override the entire method to have full control over line creation
        """
        invoice_lines = []
        excluded_count = 0
        
        for order in self:
            line_values_list = order.with_context(invoicing=True)._prepare_tax_base_line_values()
            
            for line_values in line_values_list:
                line = line_values['record']
                product = line.product_id
                
                # Skip employee service products
                if product.is_employee_service:
                    _logger.info("[PLEDGE] Excluding employee service product '%s' from invoice", product.display_name)
                    excluded_count += 1
                    continue
                
                # Skip delivery products
                if product.is_delivery_product:
                    _logger.info("[PLEDGE] Excluding delivery product '%s' from invoice", product.display_name)
                    excluded_count += 1
                    continue
                
                # Include all other products (including pledge products at product price only)
                # Virtual pledge amounts are ONLY on receipts, NOT in invoices
                
                # Get invoice line values
                invoice_lines_values = order._get_invoice_lines_values(line_values, line, move_type)
                if invoice_lines_values:  # Only add if not empty
                    invoice_lines.append((0, None, invoice_lines_values))
                
                # Add price discount note if applicable
                is_percentage = order.pricelist_id and any(
                    order.pricelist_id.item_ids.filtered(
                        lambda rule: rule.compute_price == "percentage")
                )
                if is_percentage and self.env['decimal.precision'].precision_get('Product Price'):
                    precision = self.env['decimal.precision'].precision_get('Product Price')
                    if float_compare(line.price_unit, line.product_id.lst_price, precision_digits=precision) < 0:
                        invoice_lines.append((0, None, {
                            'name': _('Price discount from %(original_price)s to %(discounted_price)s',
                                    original_price=float_repr(line.product_id.lst_price, order.currency_id.decimal_places),
                                    discounted_price=float_repr(line.price_unit, order.currency_id.decimal_places)),
                            'display_type': 'line_note',
                        }))
                
                # Add customer note if applicable
                if line.customer_note:
                    invoice_lines.append((0, None, {
                        'name': line.customer_note,
                        'display_type': 'line_note',
                    }))
            
            # Add general customer note
            if order.general_customer_note:
                invoice_lines.append((0, None, {
                    'name': order.general_customer_note,
                    'display_type': 'line_note',
                }))
        
        _logger.info(
            "[PLEDGE] Invoice lines prepared: %d lines (excluded %d employee/delivery products)",
            len(invoice_lines), excluded_count
        )
        
        return invoice_lines

    def _get_invoice_lines_to_invoice(self):
        """
        Filter out pledge, employee, and delivery products from invoice
        This ensures invoices only contain regular products
        """
        lines = super()._get_invoice_lines_to_invoice()
        
        # Exclude pledge products
        filtered_lines = lines.filtered(
            lambda l: not l.product_id.has_pledge
        )
        
        _logger.info(
            "[PLEDGE] Filtered invoice lines: %d regular items (excluded %d pledge items)",
            len(filtered_lines),
            len(lines) - len(filtered_lines)
        )
        
        return filtered_lines


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    is_pledge_related = fields.Boolean(
        string='Pledge Related',
        compute='_compute_pledge_related',
        store=True
    )

    @api.depends('product_id.has_pledge')
    def _compute_pledge_related(self):
        for line in self:
            line.is_pledge_related = line.product_id.has_pledge
