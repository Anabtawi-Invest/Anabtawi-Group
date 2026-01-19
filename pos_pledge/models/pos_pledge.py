# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PosPledge(models.Model):
    _name = 'pos.pledge'
    _description = 'POS Pledge (Rahn) Record'
    _order = 'create_date desc'

    name = fields.Char(
        string='Pledge Reference',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('New')
    )

    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
        required=True,
        ondelete='cascade'
    )

    pos_config_id = fields.Many2one(
        'pos.config',
        string='POS Configuration',
        required=True,
        readonly=True
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        help='Employee associated with this order'
    )

    pledge_products = fields.Many2many(
        'product.product',
        string='Pledge Products',
        domain=[('is_pledge_product', '=', True)]
    )

    employee_product_id = fields.Many2one(
        'product.product',
        string='Employee Service',
        domain=[('is_employee_service', '=', True)]
    )

    delivery_product_id = fields.Many2one(
        'product.product',
        string='Delivery Service',
        domain=[('is_delivery_service', '=', True)]
    )

    pledge_amount = fields.Monetary(
        string='Pledge Amount',
        required=True
    )

    employee_amount = fields.Monetary(
        string='Employee Service Amount'
    )

    delivery_amount = fields.Monetary(
        string='Delivery Service Amount'
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True
    )

    state = fields.Selection([
        ('active', 'Active'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='active', required=True)

    # Payment tracking fields (replacing journal entry fields)
    pledge_payment_id = fields.Many2one(
        'account.payment',
        string='Pledge Payment',
        readonly=True,
        help='Independent payment for pledge amount'
    )

    employee_payment_id = fields.Many2one(
        'account.payment',
        string='Employee Payment',
        readonly=True,
        help='Independent payment for employee service'
    )

    delivery_payment_id = fields.Many2one(
        'account.payment',
        string='Delivery Payment',
        readonly=True,
        help='Independent payment for delivery service'
    )

    return_payment_id = fields.Many2one(
        'account.payment',
        string='Return/Refund Payment',
        readonly=True,
        help='Reverse payment created when pledge is returned'
    )

    # Legacy journal entry fields (kept for backward compatibility)
    pledge_move_id = fields.Many2one(
        'account.move',
        string='Pledge Journal Entry (Legacy)',
        readonly=True
    )

    employee_move_id = fields.Many2one(
        'account.move',
        string='Employee Journal Entry (Legacy)',
        readonly=True
    )

    delivery_move_id = fields.Many2one(
        'account.move',
        string='Delivery Journal Entry (Legacy)',
        readonly=True
    )

    return_move_id = fields.Many2one(
        'account.move',
        string='Return Journal Entry (Legacy)',
        readonly=True
    )

    return_date = fields.Datetime(
        string='Return Date',
        readonly=True
    )

    case_type = fields.Selection([
        ('case1', 'Case 1: Employee Only'),
        ('case2', 'Case 2: Pledge Only'),
        ('case3', 'Case 3: Pledge + Delivery'),
        ('case4', 'Case 4: Pledge + Employee + Delivery'),
        ('case5', 'Case 5: Pledge + Employee'),
        ('case6', 'Case 6: Employee + Delivery'),
        ('mixed', 'Mixed Scenario'),
    ], string='Business Case', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to generate sequence for pledge records"""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pos.pledge') or _('New')
        return super().create(vals_list)

    @api.model
    def create_from_pos(self, vals):
        """
        Create pledge record from POS with accounting entries
        
        Expected vals:
        - pos_order_id: POS order ID
        - partner_id: Customer ID
        - case_type: 'case1', 'case2', or 'case3'
        - pledge_amount: Float
        - employee_amount: Float
        - delivery_amount: Float
        - pledge_products: List of product IDs
        - employee_product_id: Product ID or None
        - delivery_product_id: Product ID or None
        """
        pos_order_id = vals.get('pos_order_id')
        partner_id = vals.get('partner_id')
        case_type = vals.get('case_type')
        
        if not pos_order_id or not partner_id or not case_type:
            raise ValidationError(_('Missing required fields for pledge creation'))
        
        pos_order = self.env['pos.order'].browse(pos_order_id)
        if not pos_order.exists():
            raise ValidationError(_('POS Order not found'))
        
        # Get POS config accounts
        pos_config = pos_order.config_id
        pledge_account = pos_config.pledge_account_id
        services_account = pos_config.services_account_id
        services_journal = pos_config.services_journal_id
        
        if not services_journal:
            raise ValidationError(_('Please configure Services Journal in POS Configuration'))
        
        # Validate accounts based on case type
        if case_type == 'case1':
            # Employee service requires services_account
            if not services_account:
                raise ValidationError(_('Please configure Services Account in POS Configuration'))
        elif case_type in ('case2', 'case3', 'case4', 'case5'):
            # Pledge requires pledge_account
            if not pledge_account:
                raise ValidationError(_('Please configure Pledge Account in POS Configuration'))
            # Delivery in case3 and case4 requires services_account
            if case_type in ('case3', 'case4') and not services_account:
                raise ValidationError(_('Please configure Services Account in POS Configuration'))
            # Employee in case4, case5, case6 requires services_account
            if case_type in ('case4', 'case5', 'case6') and not services_account:
                raise ValidationError(_('Please configure Services Account in POS Configuration'))
        elif case_type == 'case6':
            # Employee + Delivery requires services_account
            if not services_account:
                raise ValidationError(_('Please configure Services Account in POS Configuration'))
        
        # Validate journal default account
        if not services_journal.default_account_id:
            raise ValidationError(_('Services Journal must have a default account configured'))
        
        # Create pledge record
        # Handle employee_product_id and delivery_product_id (convert false/None to False)
        employee_product_id = vals.get('employee_product_id')
        if not employee_product_id or employee_product_id is False:
            employee_product_id = False
        
        delivery_product_id = vals.get('delivery_product_id')
        if not delivery_product_id or delivery_product_id is False:
            delivery_product_id = False
        
        pledge_vals = {
            'pos_order_id': pos_order_id,
            'pos_config_id': pos_config.id,
            'partner_id': partner_id,
            'employee_id': pos_order.employee_id.id if pos_order.employee_id else False,
            'case_type': case_type,
            'pledge_amount': vals.get('pledge_amount', 0) or 0,
            'employee_amount': vals.get('employee_amount', 0) or 0,
            'delivery_amount': vals.get('delivery_amount', 0) or 0,
            'pledge_products': [(6, 0, vals.get('pledge_products', []) or [])],
            'employee_product_id': employee_product_id,
            'delivery_product_id': delivery_product_id,
            'company_id': pos_order.company_id.id,
        }
        
        pledge = self.create(pledge_vals)
        
        # Create accounting entries based on case type
        try:
            if case_type == 'case1':
                # Employee service entry
                if pledge.employee_amount > 0:
                    pledge.employee_move_id = pledge._create_service_entry(
                        pledge.employee_amount,
                        services_account,
                        services_journal,
                        _('Employee Service: %s') % pledge.name
                    )
            
            elif case_type == 'case2':
                # Pledge entry only
                if pledge.pledge_amount > 0:
                    pledge.pledge_move_id = pledge._create_pledge_entry(
                        pledge.pledge_amount,
                        pledge_account,
                        services_journal
                    )
            
            elif case_type == 'case3':
                # Both pledge and delivery entries
                if pledge.pledge_amount > 0:
                    pledge.pledge_move_id = pledge._create_pledge_entry(
                        pledge.pledge_amount,
                        pledge_account,
                        services_journal
                    )
                
                if pledge.delivery_amount > 0:
                    pledge.delivery_move_id = pledge._create_service_entry(
                        pledge.delivery_amount,
                        services_account,
                        services_journal,
                        _('Delivery Service: %s') % pledge.name
                    )
            
            elif case_type == 'case4':
                # All three: Pledge + Employee + Delivery
                if pledge.pledge_amount > 0:
                    pledge.pledge_move_id = pledge._create_pledge_entry(
                        pledge.pledge_amount,
                        pledge_account,
                        services_journal
                    )
                
                if pledge.employee_amount > 0:
                    pledge.employee_move_id = pledge._create_service_entry(
                        pledge.employee_amount,
                        services_account,
                        services_journal,
                        _('Employee Service: %s') % pledge.name
                    )
                
                if pledge.delivery_amount > 0:
                    pledge.delivery_move_id = pledge._create_service_entry(
                        pledge.delivery_amount,
                        services_account,
                        services_journal,
                        _('Delivery Service: %s') % pledge.name
                    )
            
            elif case_type == 'case5':
                # Pledge + Employee
                if pledge.pledge_amount > 0:
                    pledge.pledge_move_id = pledge._create_pledge_entry(
                        pledge.pledge_amount,
                        pledge_account,
                        services_journal
                    )
                
                if pledge.employee_amount > 0:
                    pledge.employee_move_id = pledge._create_service_entry(
                        pledge.employee_amount,
                        services_account,
                        services_journal,
                        _('Employee Service: %s') % pledge.name
                    )
            
            elif case_type == 'case6':
                # Employee + Delivery
                if pledge.employee_amount > 0:
                    pledge.employee_move_id = pledge._create_service_entry(
                        pledge.employee_amount,
                        services_account,
                        services_journal,
                        _('Employee Service: %s') % pledge.name
                    )
                
                if pledge.delivery_amount > 0:
                    pledge.delivery_move_id = pledge._create_service_entry(
                        pledge.delivery_amount,
                        services_account,
                        services_journal,
                        _('Delivery Service: %s') % pledge.name
                    )
        except Exception as e:
            _logger.error("[PLEDGE] Error creating journal entries for pledge %s: %s", pledge.name, str(e))
            # Rollback pledge creation if journal entries fail
            pledge.unlink()
            raise ValidationError(_('Failed to create accounting entries: %s') % str(e))
        
        # Update pos_order.pledge_id link
        pos_order.write({'pledge_id': pledge.id})
        
        # Trigger payment creation immediately (will skip if already created)
        _logger.info("[PLEDGE] Triggering payment creation for pledge %s", pledge.name)
        try:
            pos_order._create_pledge_payments()
            _logger.info("[PLEDGE] ✓ Payments created successfully for pledge %s", pledge.name)
        except Exception as e:
            _logger.error("[PLEDGE] ✗ Failed to create payments for pledge %s: %s", pledge.name, e)
        
        # NOTE: Payment linking disabled per user request
        # Payments are created but not automatically linked to pledge record
        
        return pledge.id

    def _create_pledge_entry(self, amount, pledge_account, journal):
        """Create journal entry for pledge (liability)"""
        self.ensure_one()
        
        if not pledge_account:
            raise ValidationError(_('Pledge Account is required for pledge entries'))
        
        if not journal.default_account_id:
            raise ValidationError(_('Journal default account is required'))
        
        move = self.env['account.move'].sudo().create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': _('Pledge: %s') % self.name,
            'line_ids': [
                # Debit: Cash/Bank (from journal)
                (0, 0, {
                    'name': _('Pledge Received: %s') % self.name,
                    'partner_id': self.partner_id.id,
                    'account_id': journal.default_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                # Credit: Pledge Liability
                (0, 0, {
                    'name': _('Pledge Liability: %s') % self.name,
                    'partner_id': self.partner_id.id,
                    'account_id': pledge_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def _create_service_entry(self, amount, services_account, journal, description):
        """Create journal entry for employee/delivery service"""
        self.ensure_one()
        
        if not services_account:
            raise ValidationError(_('Services Account is required for service entries'))
        
        if not journal.default_account_id:
            raise ValidationError(_('Journal default account is required'))
        
        move = self.env['account.move'].sudo().create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': description,
            'line_ids': [
                # Debit: Cash/Bank (from journal)
                (0, 0, {
                    'name': description,
                    'partner_id': self.partner_id.id,
                    'account_id': journal.default_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                # Credit: Services Income
                (0, 0, {
                    'name': description,
                    'partner_id': self.partner_id.id,
                    'account_id': services_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def action_return_pledge(self):
        """
        Handle pledge return with reverse payment
        Creates an outbound payment to refund the pledge amount
        Gets return_type from context: 'employee' or 'customer'
        """
        self.ensure_one()
        
        # Get return_type from context (default to 'customer' if not provided)
        return_type = self.env.context.get('return_type', 'customer')
        _logger.info("[PLEDGE] action_return_pledge called for pledge %s with return_type: %s", self.name, return_type)
        
        if self.state != 'active':
            raise ValidationError(_('Only active pledges can be returned'))
        
        _logger.info("[PLEDGE] Processing return with return_type: %s for pledge %s", return_type, self.name)
        _logger.info("[PLEDGE]   - pledge_payment_id: %s", self.pledge_payment_id.id if self.pledge_payment_id else 'None')
        _logger.info("[PLEDGE]   - pledge_move_id: %s", self.pledge_move_id.id if self.pledge_move_id else 'None')
        
        # Try to create payments if they don't exist (optional - not required for return)
        if not self.pledge_payment_id and not self.pledge_move_id:
            _logger.info("[PLEDGE] No payment found for pledge %s, attempting to create payments...", self.name)
            
            # Try to trigger payment creation from the POS order
            if self.pos_order_id and not self.pos_order_id.pledge_payments_created:
                try:
                    self.pos_order_id._create_pledge_payments()
                    _logger.info("[PLEDGE] Successfully created payments for pledge %s", self.name)
                    # Refresh the record to get the updated payment_id
                    self.invalidate_cache()
                    self.refresh()
                except Exception as e:
                    _logger.warning("[PLEDGE] Failed to create payments (will create refund directly): %s", e)
        
        # Use new payment system if pledge_payment_id exists, else create refund directly
        if self.pledge_payment_id:
            _logger.info("[PLEDGE] Using existing payment for refund")
            return self._return_pledge_with_payment(return_type=return_type)
        elif self.pledge_move_id:
            _logger.info("[PLEDGE] Using legacy journal entry for refund")
            return self._return_pledge_legacy(return_type=return_type)
        else:
            # No payment or move exists - create refund payment directly
            _logger.info("[PLEDGE] No existing payment found, creating refund payment directly...")
            return self._return_pledge_with_payment(return_type=return_type)
    
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

    def _return_pledge_with_payment(self, return_type='customer'):
        """Create reverse payment for pledge refund"""
        self.ensure_one()
        
        return_type_label = _('Employee Pledge') if return_type == 'employee' else _('Customer Pledge')
        _logger.info("[PLEDGE] Starting pledge return for %s (Type: %s)", self.name, return_type_label)
        _logger.info("[PLEDGE]   - Pledge amount: %s", self.pledge_amount)
        _logger.info("[PLEDGE]   - Partner: %s", self.partner_id.name)
        
        # Get the POS config and journal
        config = self.pos_order_id.config_id
        if not config.services_journal_id:
            raise ValidationError(_('No services journal configured for POS'))
        
        journal = config.services_journal_id
        _logger.info("[PLEDGE]   - Using journal: %s", journal.name)
        
        # Get pos.session from pos_order_id
        pos_session = self.pos_order_id.session_id
        if not pos_session:
            raise ValidationError(_('No POS session found for order %s') % self.pos_order_id.name)
        
        # Get outbound payment method
        outbound_methods = journal.outbound_payment_method_line_ids
        _logger.info("[PLEDGE]   - Found %d outbound payment methods", len(outbound_methods))
        
        if not outbound_methods:
            raise ValidationError(_(
                'Journal "%s" has no outbound payment methods configured. '
                'Please add a "Manual" outbound payment method to this journal in Accounting settings.'
            ) % journal.name)
        
        payment_method_line_id = outbound_methods[0].id
        _logger.info("[PLEDGE]   - Using payment method: %s", outbound_methods[0].name)
        
        # Get pos.payment.method
        pos_payment_method = self._get_pos_payment_method_from_journal(journal, config)
        
        # Use existing pos.order or create a simple one
        pos_order = self.pos_order_id
        
        try:
            # Create account.payment for accounting
            payment_vals = {
                'payment_type': 'outbound',  # We pay back to customer
                'partner_type': 'customer',
                'partner_id': self.partner_id.id,
                'amount': self.pledge_amount,
                'currency_id': self.currency_id.id,
                'journal_id': journal.id,
                'date': fields.Date.context_today(self),
                'memo': _('Pledge Refund (%s): %s') % (return_type_label, self.name),
                'payment_method_line_id': payment_method_line_id,
            }
            
            refund_payment = self.env['account.payment'].create(payment_vals)
            _logger.info("[PLEDGE]   - ✓ Refund account.payment created: %s", refund_payment.name)
            
            refund_payment.action_post()
            _logger.info("[PLEDGE]   - ✓ Refund account.payment posted")
            
            # Create pos.payment (negative amount for refund)
            refund_pos_payment = self.env['pos.payment'].sudo().create({
                'pos_order_id': pos_order.id,
                'payment_method_id': pos_payment_method.id,
                'amount': -self.pledge_amount,  # Negative for refund
                'payment_date': fields.Datetime.now(),
            })
            _logger.info("[PLEDGE]   - ✓ Refund pos.payment created: %s", refund_pos_payment.id)
            
            self.write({
                'return_payment_id': refund_payment.id,
                'return_date': fields.Datetime.now(),
                'state': 'returned'
            })
            _logger.info("[PLEDGE]   - ✓ Pledge marked as returned")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Pledge %s has been returned. Refund payment: %s') % (self.name, refund_payment.name),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error("[PLEDGE] ✗ Error creating refund payment: %s", e, exc_info=True)
            raise ValidationError(_('Failed to create refund payment: %s') % str(e))
    
    def _return_pledge_legacy(self, return_type='customer'):
        """Legacy method for journal entry-based returns"""
        self.ensure_one()
        
        return_type_label = _('Employee Pledge') if return_type == 'employee' else _('Customer Pledge')
        _logger.info("[PLEDGE] Starting legacy pledge return for %s (Type: %s)", self.name, return_type_label)

        # Create reversal entry for pledge
        if self.pledge_move_id:
            reversal = self.pledge_move_id._reverse_moves(
                default_values_list=[{
                    'date': fields.Date.context_today(self),
                    'ref': _('Pledge Return (%s): %s') % (return_type_label, self.name),
                }]
            )
            self.return_move_id = reversal.id

        # Create reversal entry for employee if exists
        if self.employee_move_id:
            self.employee_move_id._reverse_moves(
                default_values_list=[{
                    'date': fields.Date.context_today(self),
                    'ref': _('Employee Service Return: %s') % self.name,
                }]
            )

        self.write({
            'state': 'returned',
            'return_date': fields.Datetime.now()
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Pledge returned successfully (legacy mode)'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        """Cancel the pledge"""
        self.write({'state': 'cancelled'})
    
    def action_link_payments(self):
        """Manually link payments to this pledge record"""
        self.ensure_one()
        
        if not self.pos_order_id:
            raise ValidationError(_('No POS order associated with this pledge'))
        
        try:
            self._link_payments_from_order(self.pos_order_id)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Payments linked successfully'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error("[PLEDGE] Error linking payments: %s", e, exc_info=True)
            raise ValidationError(_('Failed to link payments: %s') % str(e))
    
    def _link_payments_from_order(self, pos_order):
        """
        Link payments created for this order to the pledge record
        Searches for payments with memo matching the order
        """
        self.ensure_one()
        
        try:
            _logger.info("[PLEDGE] ========================================")
            _logger.info("[PLEDGE] Linking payments to pledge record %s from order %s", self.name, pos_order.name)
            _logger.info("[PLEDGE] Partner: %s (ID: %s)", self.partner_id.name if self.partner_id else 'None', self.partner_id.id if self.partner_id else 'None')
            _logger.info("[PLEDGE] Order name: %s", pos_order.name if pos_order else 'None')
            
            # Search for all payments for this partner (more flexible search)
            # Search by partner and date (today or order date)
            search_date = fields.Date.today()
            if pos_order.date_order:
                try:
                    if hasattr(pos_order.date_order, 'date'):
                        search_date = pos_order.date_order.date()
                    else:
                        from datetime import datetime
                        search_date = datetime.strptime(str(pos_order.date_order).split()[0], '%Y-%m-%d').date()
                except:
                    search_date = fields.Date.today()
            
            base_domain = [
                ('partner_id', '=', self.partner_id.id),
                ('state', '=', 'posted'),
                ('date', '>=', search_date),
                ('date', '<=', search_date),
            ]
            
            # Search for all payments with order name in memo
            all_payments = self.env['account.payment'].search(
                base_domain + [('memo', 'ilike', pos_order.name)],
                order='create_date desc'
            )
            
            _logger.info("[PLEDGE] Searching for payments with date: %s", search_date)
            _logger.info("[PLEDGE] Found %d payments with order name in memo", len(all_payments))
            
            # If no payments found, try searching by amount matching (more reliable)
            if not all_payments:
                _logger.info("[PLEDGE] No payments found by memo, trying amount-based search...")
                
                # Search for payments matching the amounts
                if self.pledge_amount > 0:
                    pledge_payments = self.env['account.payment'].search([
                        ('partner_id', '=', self.partner_id.id),
                        ('state', '=', 'posted'),
                        ('amount', '=', self.pledge_amount),
                        ('payment_type', '=', 'inbound'),
                    ], order='create_date desc', limit=5)
                    _logger.info("[PLEDGE] Found %d payments with pledge amount %.2f", len(pledge_payments), self.pledge_amount)
                    for pay in pledge_payments:
                        _logger.info("[PLEDGE]   - Payment: %s, Memo: %s, Amount: %s", pay.name, pay.memo, pay.amount)
                
                # Also try searching all payments for this partner in last 10 minutes
                from datetime import datetime, timedelta
                ten_minutes_ago = datetime.now() - timedelta(minutes=10)
                recent_payments = self.env['account.payment'].search([
                    ('partner_id', '=', self.partner_id.id),
                    ('state', '=', 'posted'),
                    ('create_date', '>=', ten_minutes_ago.strftime('%Y-%m-%d %H:%M:%S')),
                ], order='create_date desc')
                _logger.info("[PLEDGE] Found %d payments for partner in last 10 minutes", len(recent_payments))
                for pay in recent_payments:
                    _logger.info("[PLEDGE]   - Payment: %s, Memo: %s, Amount: %s, Created: %s", 
                                pay.name, pay.memo, pay.amount, pay.create_date)
                
                # Filter by amounts if we have them
                if recent_payments:
                    matching_payments = recent_payments.filtered(lambda p: 
                        (self.pledge_amount > 0 and abs(p.amount - self.pledge_amount) < 0.01) or
                        (self.employee_amount > 0 and abs(p.amount - self.employee_amount) < 0.01) or
                        (self.delivery_amount > 0 and abs(p.amount - self.delivery_amount) < 0.01)
                    )
                    if matching_payments:
                        all_payments = matching_payments
                        _logger.info("[PLEDGE] Found %d payments matching amounts", len(matching_payments))
                    else:
                        all_payments = recent_payments
            
            for pay in all_payments:
                _logger.info("[PLEDGE]   - Payment: %s, Memo: %s, Amount: %s, Date: %s", 
                            pay.name, pay.memo, pay.amount, pay.date)
            
            # Search for pledge payment
            if self.pledge_amount > 0 and not self.pledge_payment_id:
                pledge_payments = all_payments.filtered(lambda p: 'Pledge' in (p.memo or ''))
                if not pledge_payments:
                    # Try more flexible search
                    pledge_payments = self.env['account.payment'].search(
                        base_domain + [
                            ('memo', 'ilike', pos_order.name),
                            ('memo', 'ilike', 'Pledge')
                        ],
                        order='create_date desc',
                        limit=1
                    )
                
                if pledge_payments:
                    pledge_payment = pledge_payments[0] if isinstance(pledge_payments, list) else pledge_payments
                    self.write({'pledge_payment_id': pledge_payment.id})
                    _logger.info("[PLEDGE] ✓ Linked pledge payment %s to pledge %s", 
                                pledge_payment.name, self.name)
                else:
                    _logger.warning("[PLEDGE] ⚠️ No pledge payment found for order %s", pos_order.name)
            
            # Search for employee payment
            if self.employee_amount > 0 and not self.employee_payment_id:
                employee_payments = all_payments.filtered(lambda p: 'Employee' in (p.memo or ''))
                if not employee_payments:
                    # Try more flexible search
                    employee_payments = self.env['account.payment'].search(
                        base_domain + [
                            ('memo', 'ilike', pos_order.name),
                            ('memo', 'ilike', 'Employee')
                        ],
                        order='create_date desc',
                        limit=1
                    )
                
                if employee_payments:
                    employee_payment = employee_payments[0] if isinstance(employee_payments, list) else employee_payments
                    self.write({'employee_payment_id': employee_payment.id})
                    _logger.info("[PLEDGE] ✓ Linked employee payment %s to pledge %s", 
                                employee_payment.name, self.name)
                else:
                    _logger.warning("[PLEDGE] ⚠️ No employee payment found for order %s", pos_order.name)
            
            # Search for delivery payment
            if self.delivery_amount > 0 and not self.delivery_payment_id:
                delivery_payments = all_payments.filtered(lambda p: 'Delivery' in (p.memo or ''))
                if not delivery_payments:
                    # Try more flexible search
                    delivery_payments = self.env['account.payment'].search(
                        base_domain + [
                            ('memo', 'ilike', pos_order.name),
                            ('memo', 'ilike', 'Delivery')
                        ],
                        order='create_date desc',
                        limit=1
                    )
                
                if delivery_payments:
                    delivery_payment = delivery_payments[0] if isinstance(delivery_payments, list) else delivery_payments
                    self.write({'delivery_payment_id': delivery_payment.id})
                    _logger.info("[PLEDGE] ✓ Linked delivery payment %s to pledge %s", 
                                delivery_payment.name, self.name)
                else:
                    _logger.warning("[PLEDGE] ⚠️ No delivery payment found for order %s", pos_order.name)
            
            _logger.info("[PLEDGE] ========================================")
        except Exception as e:
            _logger.error("[PLEDGE] ✗ Error in _link_payments_from_order: %s", e, exc_info=True)
            raise
