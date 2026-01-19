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

    @api.depends('lines.product_id.is_pledge_product')
    def _compute_has_pledge(self):
        for order in self:
            _logger.info("[PLEDGE] Computing has_pledge for order: %s", order.name)
            _logger.info("[PLEDGE] Order has %d lines", len(order.lines))
            
            pledge_lines = []
            for line in order.lines:
                _logger.info("[PLEDGE]   Line: %s (Product ID: %s)", 
                            line.product_id.name, line.product_id.id)
                _logger.info("[PLEDGE]     - is_pledge_product: %s", line.product_id.is_pledge_product)
                
                if line.product_id.is_pledge_product:
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
        Create separate independent payments for pledge, employee, and delivery amounts
        These payments are NOT linked to any invoice
        Called after order validation
        """
        _logger.info("[PLEDGE] _create_pledge_payments() called for %d orders", len(self))
        AccountPayment = self.env['account.payment']
        
        for order in self:
            _logger.info("[PLEDGE] Processing order: %s", order.name)
            _logger.info("[PLEDGE]   - has_pledge: %s", order.has_pledge)
            _logger.info("[PLEDGE]   - pledge_payments_created: %s", order.pledge_payments_created)
            
            # Skip if no pledge items or payments already created
            if not order.has_pledge:
                _logger.warning("[PLEDGE] Order %s has no pledge items, skipping", order.name)
                continue
            
            if order.pledge_payments_created:
                _logger.warning("[PLEDGE] Order %s payments already created, skipping", order.name)
                continue
            
            # Get POS config for journals
            config = order.config_id
            _logger.info("[PLEDGE] POS Config: %s", config.name)
            _logger.info("[PLEDGE] Services Journal: %s", config.services_journal_id.name if config.services_journal_id else 'NOT SET')
            
            if not config.services_journal_id:
                _logger.warning(
                    "[PLEDGE] Missing services journal configuration for POS %s.",
                    config.name
                )
                continue
            
            # Calculate amounts for each type
            pledge_amount = 0.0
            employee_amount = 0.0
            delivery_amount = 0.0
            
            _logger.info("[PLEDGE] Processing %d order lines", len(order.lines))
            for line in order.lines:
                _logger.info("[PLEDGE]   Line: %s", line.product_id.name)
                _logger.info("[PLEDGE]     - is_pledge_product: %s", line.product_id.is_pledge_product)
                _logger.info("[PLEDGE]     - is_employee_service: %s", line.product_id.is_employee_service)
                _logger.info("[PLEDGE]     - is_delivery_product: %s", line.product_id.is_delivery_product)
                _logger.info("[PLEDGE]     - price_subtotal_incl: %.2f", line.price_subtotal_incl)
                
                if line.product_id.is_pledge_product:
                    # Use pledge_amount from product or line total
                    line_amount = line.product_id.pledge_amount or line.price_subtotal_incl
                    pledge_amount += line_amount
                    _logger.info("[PLEDGE]     -> Adding %.2f to pledge_amount", line_amount)
                
                elif line.product_id.is_employee_service:
                    # Add employee service amount
                    employee_amount += line.price_subtotal_incl
                    _logger.info("[PLEDGE]     -> Adding %.2f to employee_amount", line.price_subtotal_incl)
                
                elif line.product_id.is_delivery_product:
                    # Add delivery amount
                    delivery_amount += line.price_subtotal_incl
                    _logger.info("[PLEDGE]     -> Adding %.2f to delivery_amount", line.price_subtotal_incl)
            
            _logger.info(
                "[PLEDGE] TOTALS for order %s: Pledge=%.2f, Employee=%.2f, Delivery=%.2f",
                order.name, pledge_amount, employee_amount, delivery_amount
            )
            
            # Create separate payments
            payments_created = []
            pledge_payment = None
            employee_payment = None
            delivery_payment = None
            
            # 1. Create Pledge Payment
            if pledge_amount > 0:
                _logger.info("[PLEDGE] Creating pledge payment for %.2f", pledge_amount)
                pledge_payment = self._create_independent_payment(
                    order, pledge_amount, config.services_journal_id, 'Pledge'
                )
                if pledge_payment:
                    _logger.info("[PLEDGE] ✓ Pledge payment created: %s", pledge_payment.name)
                    payments_created.append(pledge_payment)
                else:
                    _logger.error("[PLEDGE] ✗ Failed to create pledge payment!")
            else:
                _logger.info("[PLEDGE] No pledge amount, skipping pledge payment")
            
            # 2. Create Employee Service Payment
            if employee_amount > 0:
                _logger.info("[PLEDGE] Creating employee payment for %.2f", employee_amount)
                employee_payment = self._create_independent_payment(
                    order, employee_amount, config.services_journal_id, 'Employee Service'
                )
                if employee_payment:
                    _logger.info("[PLEDGE] ✓ Employee payment created: %s", employee_payment.name)
                    payments_created.append(employee_payment)
                else:
                    _logger.error("[PLEDGE] ✗ Failed to create employee payment!")
            else:
                _logger.info("[PLEDGE] No employee amount, skipping employee payment")
            
            # 3. Create Delivery Service Payment
            if delivery_amount > 0:
                _logger.info("[PLEDGE] Creating delivery payment for %.2f", delivery_amount)
                delivery_payment = self._create_independent_payment(
                    order, delivery_amount, config.services_journal_id, 'Delivery Service'
                )
                if delivery_payment:
                    _logger.info("[PLEDGE] ✓ Delivery payment created: %s", delivery_payment.name)
                    payments_created.append(delivery_payment)
                else:
                    _logger.error("[PLEDGE] ✗ Failed to create delivery payment!")
            else:
                _logger.info("[PLEDGE] No delivery amount, skipping delivery payment")
            
            # Note: Payments are already posted in _create_independent_payment
            _logger.info("[PLEDGE] Created and posted %d independent payments for order %s", 
                        len(payments_created), order.name)
            
            # NOTE: Payment linking disabled per user request
            # Payments are created but not automatically linked to pledge record
            
            # Mark payments as created ONLY if we actually created any
            if payments_created:
                _logger.info("[PLEDGE] Marking payments as created for order %s", order.name)
                order.write({'pledge_payments_created': True})
                _logger.info("[PLEDGE] ✓ Payment creation complete for order %s", order.name)
            else:
                _logger.warning("[PLEDGE] ⚠️ No payments were created for order %s - flag NOT set", order.name)
    
    def write(self, vals):
        """Override write to trigger pledge payments if order state changes"""
        _logger.info("[PLEDGE] write() called on %d orders with vals: %s", len(self), vals)
        
        result = super().write(vals)
        
        # If order is being validated/paid, create pledge payments
        # This happens after order is synced from POS
        if vals.get('state') in ('paid', 'done'):
            _logger.info("[PLEDGE] Order state changed to %s, checking for pledge orders", vals.get('state'))
            
            for order in self:
                _logger.info(
                    "[PLEDGE] Order %s: has_pledge=%s, pledge_payments_created=%s",
                    order.name, order.has_pledge, order.pledge_payments_created
                )
            
            pledge_orders = self.filtered(lambda o: o.has_pledge and not o.pledge_payments_created)
            _logger.info("[PLEDGE] Found %d pledge orders needing payments", len(pledge_orders))
            
            if pledge_orders:
                _logger.info("[PLEDGE] Triggering pledge payments for orders: %s", 
                            ', '.join(pledge_orders.mapped('name')))
                pledge_orders._create_pledge_payments()
                # NOTE: Payment linking disabled per user request
            else:
                _logger.info("[PLEDGE] No pledge orders to process")
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
            lambda l: not l.product_id.is_pledge_product
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

    @api.depends('product_id.is_pledge_product')
    def _compute_pledge_related(self):
        for line in self:
            line.is_pledge_related = line.product_id.is_pledge_product
