# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from collections import defaultdict
from odoo.tools import float_is_zero, frozendict
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

# Log when module is loaded
_logger.info("=" * 80)
_logger.info("[ADVANCE MODULE] Module enbtawi.advance.pos_session loaded successfully")
_logger.info("=" * 80)


class PosSession(models.Model):
    _inherit = 'pos.session'
    
    # Log when class is defined
    _logger.info("[ADVANCE MODULE] PosSession class inherited in enbtawi.advance")

    def action_pos_session_closing_control(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """
        Override to add logging at the entry point
        """
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] action_pos_session_closing_control called for session: %s (ID: %d)", self.name, self.id)
        _logger.info("[ADVANCE SESSION CLOSE] Parameters - balancing_account: %s, amount_to_balance: %.2f",
                    balancing_account.name if balancing_account else "None", amount_to_balance)
        
        result = super().action_pos_session_closing_control(balancing_account, amount_to_balance, bank_payment_method_diffs)
        
        _logger.info("[ADVANCE SESSION CLOSE] action_pos_session_closing_control completed, result type: %s", type(result))
        return result

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """
        Override to add logging before closing session
        """
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] _validate_session called for session: %s (ID: %d)", self.name, self.id)
        _logger.info("[ADVANCE SESSION CLOSE] Parameters - balancing_account: %s, amount_to_balance: %.2f",
                    balancing_account.name if balancing_account else "None", amount_to_balance)
        
        # Count account.payment records before closing
        account_payments_before = self.env['account.payment'].search_count([
            ('pos_session_id', '=', self.id),
        ])
        _logger.info("[ADVANCE SESSION CLOSE] account.payment records before closing: %d", account_payments_before)
        
        # Count advance orders and their payments
        advance_orders = self.order_ids.filtered(lambda o: getattr(o, 'is_advance_order', False))
        advance_account_payments = self.env['account.payment'].search([
            ('pos_session_id', '=', self.id),
        ]).filtered(lambda p: p.pos_order_id and getattr(p.pos_order_id, 'is_advance_order', False))
        _logger.info("[ADVANCE SESSION CLOSE] Advance orders in session: %d", len(advance_orders))
        _logger.info("[ADVANCE SESSION CLOSE] Advance account.payment records: %d", len(advance_account_payments))
        
        if advance_account_payments:
            _logger.info("[ADVANCE SESSION CLOSE] Advance account.payment details:")
            for payment in advance_account_payments:
                _logger.info("  - Payment ID: %d, Name: %s, Amount: %.2f, State: %s, Order: %s", 
                           payment.id, payment.name, payment.amount, payment.state,
                           payment.pos_order_id.name if payment.pos_order_id else "None")
        
        # Call parent method
        result = super()._validate_session(balancing_account, amount_to_balance, bank_payment_method_diffs)
        
        # Count account.payment records after closing
        account_payments_after = self.env['account.payment'].search_count([
            ('pos_session_id', '=', self.id),
        ])
        _logger.info("[ADVANCE SESSION CLOSE] account.payment records after closing: %d (New: %d)", 
                    account_payments_after, account_payments_after - account_payments_before)
        
        if account_payments_after > account_payments_before:
            new_payments = self.env['account.payment'].search([
                ('pos_session_id', '=', self.id),
            ], order='create_date desc', limit=account_payments_after - account_payments_before)
            _logger.info("[ADVANCE SESSION CLOSE] ⚠️ New account.payment records created during closing:")
            for payment in new_payments:
                is_advance = payment.pos_order_id and getattr(payment.pos_order_id, 'is_advance_order', False)
                _logger.info("  - Payment ID: %d, Name: %s, Amount: %.2f, State: %s, Order: %s, Is Advance: %s", 
                           payment.id, payment.name, payment.amount, payment.state,
                           payment.pos_order_id.name if payment.pos_order_id else "None", is_advance)
                if is_advance:
                    _logger.error("[ADVANCE SESSION CLOSE] ⚠️ ERROR: account.payment created for advance order during closing!")
        else:
            _logger.info("[ADVANCE SESSION CLOSE] ✓ No new account.payment records created during closing (expected)")
        
        # Summary of all payments in session
        all_account_payments = self.env['account.payment'].search([
            ('pos_session_id', '=', self.id),
        ])
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] FINAL PAYMENT SUMMARY for Session: %s (ID: %d)", self.name, self.id)
        _logger.info("[ADVANCE SESSION CLOSE] Total account.payment records: %d", len(all_account_payments))
        
        advance_payments_summary = all_account_payments.filtered(
            lambda p: p.pos_order_id and getattr(p.pos_order_id, 'is_advance_order', False)
        )
        regular_payments_summary = all_account_payments - advance_payments_summary
        
        _logger.info("[ADVANCE SESSION CLOSE] Advance account.payment records: %d", len(advance_payments_summary))
        if advance_payments_summary:
            total_advance_amount = sum(advance_payments_summary.mapped('amount'))
            _logger.info("[ADVANCE SESSION CLOSE] Total advance payment amount: %.2f", total_advance_amount)
            for payment in advance_payments_summary:
                _logger.info("  - Advance Payment ID: %d, Name: %s, Amount: %.2f, State: %s, Order: %s", 
                           payment.id, payment.name, payment.amount, payment.state,
                           payment.pos_order_id.name if payment.pos_order_id else "None")
        
        _logger.info("[ADVANCE SESSION CLOSE] Regular account.payment records: %d", len(regular_payments_summary))
        if regular_payments_summary:
            total_regular_amount = sum(regular_payments_summary.mapped('amount'))
            _logger.info("[ADVANCE SESSION CLOSE] Total regular payment amount: %.2f", total_regular_amount)
        
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] _validate_session completed")
        return result

    def _close_session_action(self, amount_to_balance):
        """
        Override to add logging when Force Close wizard is shown
        """
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] _close_session_action called - amount_to_balance: %.2f", amount_to_balance)
        
        result = super()._close_session_action(amount_to_balance)
        
        _logger.info("[ADVANCE SESSION CLOSE] Force Close wizard created and returned")
        _logger.info("[ADVANCE SESSION CLOSE] Wizard action: %s", result)
        
        return result

    def _get_closed_orders(self):
        """
        Override to exclude advance orders from account move calculations
        but keep them for payment tracking
        """
        orders = super()._get_closed_orders()
        # Filter out advance orders for account move calculations
        # But we'll handle payments separately in _accumulate_amounts
        return orders

    def _create_picking_at_end_of_session(self):
        """
        Override to exclude advance orders from picking creation
        """
        self.ensure_one()
        lines_grouped_by_dest_location = {}
        picking_type = self.config_id.picking_type_id

        if not picking_type or not picking_type.default_location_dest_id:
            session_destination_id = self.env['stock.warehouse']._get_partner_locations()[0].id
        else:
            session_destination_id = picking_type.default_location_dest_id.id

        # Filter out advance orders
        for order in self._get_closed_orders().filtered(lambda o: not getattr(o, 'is_advance_order', False)):
            if order.company_id.anglo_saxon_accounting and order.is_invoiced or order.shipping_date:
                continue
            destination_id = order.partner_id.property_stock_customer.id or session_destination_id
            if destination_id in lines_grouped_by_dest_location:
                lines_grouped_by_dest_location[destination_id] |= order.lines
            else:
                lines_grouped_by_dest_location[destination_id] = order.lines

        for location_dest_id, lines in lines_grouped_by_dest_location.items():
            pickings = self.env['stock.picking']._create_picking_from_pos_order_lines(location_dest_id, lines, picking_type)
            pickings.write({'pos_session_id': self.id, 'origin': self.name})

    def _accumulate_amounts(self, data):
        """
        Override to exclude advance orders (is_advance_order=True) from sales/taxes calculations
        but keep their payments for closing register display
        """
        AccountTax = self.env['account.tax']
        amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0}
        tax_amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0, 'base_amount': 0.0, 'base_amount_converted': 0.0}
        split_receivables_bank = defaultdict(amounts)
        split_receivables_cash = defaultdict(amounts)
        split_receivables_pay_later = defaultdict(amounts)
        combine_receivables_bank = defaultdict(amounts)
        combine_receivables_cash = defaultdict(amounts)
        combine_receivables_pay_later = defaultdict(amounts)
        combine_invoice_receivables = defaultdict(amounts)
        split_invoice_receivables = defaultdict(amounts)
        sales = defaultdict(amounts)
        taxes = defaultdict(tax_amounts)
        stock_expense = defaultdict(amounts)
        stock_return = defaultdict(amounts)
        stock_valuation = defaultdict(amounts)
        rounding_difference = {'amount': 0.0, 'amount_converted': 0.0}
        # Track the receivable lines of the order's invoice payment moves for reconciliation
        # These receivable lines are reconciled to the corresponding invoice receivable lines
        # of this session's move_id.
        combine_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
        split_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
        pos_receivable_account = self.company_id.account_default_pos_receivable_account_id
        currency_rounding = self.currency_id.rounding
        closed_orders = self._get_closed_orders()
        
        _logger.info("[ADVANCE SESSION CLOSE] Starting _accumulate_amounts for session %s", self.name)
        _logger.info("[ADVANCE SESSION CLOSE] Total closed orders: %d", len(closed_orders))
        
        # Count advance orders, completion orders, and their payments
        advance_orders_count = 0
        completion_orders_count = 0
        advance_payments_count = 0
        completion_payments_count = 0
        advance_payments_total = 0.0
        completion_payments_total = 0.0
        
        for order in closed_orders:
            # Skip sales/taxes calculations for advance orders, but keep payments
            # Check both is_advance_order (for initial advance orders) and advance_payment_id (for completion orders)
            is_advance_order = getattr(order, 'is_advance_order', False)
            is_completion_order = bool(order.advance_payment_id)
            is_advance_related = is_advance_order or is_completion_order
            
            if is_advance_order:
                advance_orders_count += 1
                for payment in order.payment_ids:
                    if payment.payment_method_id.type != 'pay_later':
                        advance_payments_count += 1
                        advance_payments_total += payment.amount
            
            # Also count completion orders (orders with advance_payment_id)
            if is_completion_order and not is_advance_order:
                completion_orders_count += 1
                for payment in order.payment_ids:
                    if payment.payment_method_id.type != 'pay_later':
                        completion_payments_count += 1
                        completion_payments_total += payment.amount
                _logger.info("[ADVANCE SESSION CLOSE] Found completion order: %s (ID: %d), Advance Payment ID: %d", 
                           order.name, order.id, order.advance_payment_id.id)
            
            order_is_invoiced = order.is_invoiced
            for payment in order.payment_ids:
                amount = payment.amount
                if float_is_zero(amount, precision_rounding=currency_rounding):
                    continue
                date = payment.payment_date
                payment_method = payment.payment_method_id
                is_split_payment = payment.payment_method_id.split_transactions
                payment_type = payment_method.type

                # For advance orders and completion orders, skip payment processing in session closing
                # REASON: 
                # - Advance payments: Already recorded via account.payment when created
                #   (with Debit: Cash/Bank, Credit: Advance Account)
                # - Completion payments: Already handled by Completion Move in action_create_invoice()
                #   (Completion Move records: Debit Cash/Bank + Advance Account, Credit Receivable)
                # No need to create additional journal entries during session closing
                if is_advance_related and payment_type != 'pay_later':
                    order_type = "Advance Order" if is_advance_order else "Completion Order"
                    _logger.info("[ADVANCE SESSION CLOSE] Skipping %s payment in session closing:", order_type)
                    _logger.info("  - Order: %s (ID: %d)", order.name, order.id)
                    _logger.info("  - Amount: %.2f", amount)
                    if is_advance_order:
                        _logger.info("  - Reason: Already recorded via account.payment (journal entry exists)")
                    else:
                        _logger.info("  - Reason: Already handled by Completion Move (journal entry exists)")
                    
                    # Skip - payment already has journal entry (either from account.payment or Completion Move)
                    continue

                # If not pay_later, we create the receivable vals for both invoiced and uninvoiced orders.
                #   Separate the split and aggregated payments.
                # Moreover, if the order is invoiced, we create the pos receivable vals that will balance the
                # pos receivable lines from the invoice payments.
                if payment_type != 'pay_later':
                    if is_split_payment and payment_type == 'cash':
                        split_receivables_cash[payment] = self._update_amounts(split_receivables_cash[payment], {'amount': amount}, date)
                    elif not is_split_payment and payment_type == 'cash':
                        combine_receivables_cash[payment_method] = self._update_amounts(combine_receivables_cash[payment_method], {'amount': amount}, date)
                    elif is_split_payment and payment_type == 'bank':
                        split_receivables_bank[payment] = self._update_amounts(split_receivables_bank[payment], {'amount': amount}, date)
                    elif not is_split_payment and payment_type == 'bank':
                        combine_receivables_bank[payment_method] = self._update_amounts(combine_receivables_bank[payment_method], {'amount': amount}, date)

                    # Create the vals to create the pos receivables that will balance the pos receivables from invoice payment moves.
                    if order_is_invoiced:
                        if is_split_payment:
                            split_inv_payment_receivable_lines[payment] |= payment.account_move_id.line_ids.filtered(lambda line: line.account_id == pos_receivable_account)
                            split_invoice_receivables[payment] = self._update_amounts(split_invoice_receivables[payment], {'amount': payment.amount}, order.date_order)
                        else:
                            combine_inv_payment_receivable_lines[payment_method] |= payment.account_move_id.line_ids.filtered(lambda line: line.account_id == pos_receivable_account)
                            combine_invoice_receivables[payment_method] = self._update_amounts(combine_invoice_receivables[payment_method], {'amount': payment.amount}, order.date_order)

                # If pay_later, we create the receivable lines.
                #   if split, with partner
                #   Otherwise, it's aggregated (combined)
                # But only do if order is *not* invoiced because no account move is created for pay later invoice payments.
                if payment_type == 'pay_later' and not order_is_invoiced:
                    if is_split_payment:
                        split_receivables_pay_later[payment] = self._update_amounts(split_receivables_pay_later[payment], {'amount': amount}, date)
                    elif not is_split_payment:
                        combine_receivables_pay_later[payment_method] = self._update_amounts(combine_receivables_pay_later[payment_method], {'amount': amount}, date)

            # Skip sales/taxes/stock calculations for advance orders
            if not order_is_invoiced and not is_advance_order:
                base_lines = order.with_context(linked_to_pos=True)._prepare_tax_base_line_values()
                AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
                AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
                AccountTax._add_accounting_data_in_base_lines_tax_details(base_lines, order.company_id, include_caba_tags=True)
                tax_results = AccountTax._prepare_tax_lines(base_lines, order.company_id)
                total_amount_currency = 0.0
                for base_line, to_update in tax_results['base_lines_to_update']:
                    # Combine sales/refund lines
                    sale_vals_dict = self._get_sale_key(base_line)
                    sale_key = frozendict(sale_vals_dict)
                    total_amount_currency += to_update['amount_currency']
                    sales[sale_key] = self._update_amounts(
                        sales[sale_key],
                        {
                            'amount': to_update['amount_currency'],
                            'amount_converted': to_update['balance'],
                        },
                        order.date_order,
                    )
                    if self.config_id._is_quantities_set():
                        sales[sale_key].setdefault('quantity', 0)
                        sales[sale_key]['quantity'] += base_line['quantity']

                # Combine tax lines
                for tax_line in tax_results['tax_lines_to_add']:
                    tax_key = (
                        tax_line['account_id'],
                        tax_line['tax_repartition_line_id'],
                        tuple(tax_line['tax_tag_ids'][0][2]),
                    )
                    total_amount_currency += tax_line['amount_currency']
                    taxes[tax_key] = self._update_amounts(
                        taxes[tax_key],
                        {
                            'amount': tax_line['amount_currency'],
                            'amount_converted': tax_line['balance'],
                            'base_amount': tax_line['tax_base_amount'],
                            'base_amount_converted': tax_line['base_balance'],
                        },
                        order.date_order,
                    )

                if self.config_id.cash_rounding:
                    diff = order.amount_paid + total_amount_currency
                    rounding_difference = self._update_amounts(rounding_difference, {'amount': diff}, order.date_order)

                # Increasing current partner's customer_rank
                partners = (order.partner_id | order.partner_id.commercial_partner_id)
                partners._increase_rank('customer_rank')

            # Stock valuation lines (skip for advance orders)
            if not is_advance_order:
                if self.config_id._is_quantities_set():
                    order_stock_lines = order.lines.filtered(lambda l: l.product_id.type in ('product', 'consu') and float_is_zero(l.qty, precision_rounding=currency_rounding) == False)
                    for stock_line in order_stock_lines:
                        exp_key = self._get_stock_expense_key(stock_line)
                        stock_expense[exp_key] = self._update_amounts(
                            stock_expense[exp_key],
                            {'amount': stock_line.cost_subtotal},
                            order.date_order,
                        )
                        if stock_line.product_id.type == 'product':
                            stock_return_key = self._get_stock_return_key(stock_line)
                            stock_return[stock_return_key] = self._update_amounts(
                                stock_return[stock_return_key],
                                {'amount': stock_line.cost_subtotal},
                                order.date_order,
                            )
                            stock_valuation_key = self._get_stock_valuation_key(stock_line)
                            stock_valuation[stock_valuation_key] = self._update_amounts(
                                stock_valuation[stock_valuation_key],
                                {'amount': stock_line.cost_subtotal},
                                order.date_order,
                            )

        # Handle anglo_saxon_accounting stock moves (skip advance orders)
        if self.company_id.anglo_saxon_accounting:
            all_picking_ids = self.order_ids.filtered(
                lambda p: not p.is_invoiced and not p.shipping_date and not getattr(p, 'is_advance_order', False)
            ).picking_ids.ids + self.picking_ids.filtered(lambda p: not p.pos_order_id).ids
            if all_picking_ids:
                from odoo.tools.constants import PREFETCH_MAX
                from odoo.tools import split_every
                # Combine stock lines
                stock_move_sudo = self.env['stock.move'].sudo()
                stock_moves = stock_move_sudo.search([
                    ('picking_id', 'in', all_picking_ids),
                    ('company_id.anglo_saxon_accounting', '=', True),
                    ('product_id.categ_id.property_valuation', '=', 'real_time'),
                    ('product_id.is_storable', '=', True),
                ])
                for stock_moves_batch in split_every(PREFETCH_MAX, stock_moves._ids, stock_moves.browse):
                    for move in stock_moves_batch:
                        product_accounts = move.product_id._get_product_accounts()
                        exp_key = product_accounts['expense']
                        stock_key = product_accounts['stock_valuation']
                        signed_product_qty = move.quantity
                        if move._is_in():
                            signed_product_qty *= -1
                        amount = signed_product_qty * move._get_price_unit()
                        stock_expense[exp_key] = self._update_amounts(stock_expense[exp_key], {'amount': amount}, move.picking_id.date_done, force_company_currency=True)
                        if move._is_in():
                            stock_return[stock_key] = self._update_amounts(stock_return[stock_key], {'amount': amount}, move.picking_id.date_done, force_company_currency=True)
                        else:
                            stock_valuation[stock_key] = self._update_amounts(stock_valuation[stock_key], {'amount': amount}, move.picking_id.date_done, force_company_currency=True)

        MoveLine = self.env['account.move.line'].with_context(check_move_validity=False, skip_invoice_sync=True)

        _logger.info("[ADVANCE SESSION CLOSE] Summary of _accumulate_amounts:")
        _logger.info("  - Advance orders found: %d", advance_orders_count)
        _logger.info("  - Advance payments skipped: %d (Total amount: %.2f)", advance_payments_count, advance_payments_total)
        _logger.info("  - Advance payments are NOT processed here (already recorded via account.payment)")
        _logger.info("  - Completion orders found: %d", completion_orders_count)
        _logger.info("  - Completion payments skipped: %d (Total amount: %.2f)", completion_payments_count, completion_payments_total)
        _logger.info("  - Completion payments are NOT processed here (already handled by Completion Move)")
        _logger.info("  - Regular orders processed: %d", len(closed_orders) - advance_orders_count - completion_orders_count)
        _logger.info("  - combine_receivables_bank entries: %d", len(combine_receivables_bank))
        _logger.info("  - split_receivables_bank entries: %d", len(split_receivables_bank))
        _logger.info("  - combine_receivables_cash entries: %d", len(combine_receivables_cash))
        _logger.info("  - split_receivables_cash entries: %d", len(split_receivables_cash))
        
        data.update({
            'taxes':                               taxes,
            'sales':                               sales,
            'stock_expense':                       stock_expense,
            'split_receivables_bank':              split_receivables_bank,
            'combine_receivables_bank':            combine_receivables_bank,
            'split_receivables_cash':              split_receivables_cash,
            'combine_receivables_cash':            combine_receivables_cash,
            'combine_invoice_receivables':         combine_invoice_receivables,
            'split_receivables_pay_later':         split_receivables_pay_later,
            'combine_receivables_pay_later':       combine_receivables_pay_later,
            'stock_return':                        stock_return,
            'stock_valuation':                     stock_valuation,
            'combine_inv_payment_receivable_lines': combine_inv_payment_receivable_lines,
            'rounding_difference':                 rounding_difference,
            'MoveLine':                            MoveLine,
            'split_invoice_receivables': split_invoice_receivables,
            'split_inv_payment_receivable_lines': split_inv_payment_receivable_lines,
        })
        return data

    def _create_account_move(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """
        Override to create balanced accounting entry for advance payments
        """
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] _create_account_move called for session: %s (ID: %d)", self.name, self.id)
        _logger.info("[ADVANCE SESSION CLOSE] Parameters - balancing_account: %s, amount_to_balance: %.2f",
                    balancing_account.name if balancing_account else "None", amount_to_balance)
        
        # Check for advance and completion orders in session
        all_orders = self.order_ids
        advance_orders = all_orders.filtered(lambda o: getattr(o, 'is_advance_order', False))
        completion_orders = all_orders.filtered(lambda o: o.advance_payment_id and not getattr(o, 'is_advance_order', False))
        _logger.info("[ADVANCE SESSION CLOSE] Total orders in session: %d", len(all_orders))
        _logger.info("[ADVANCE SESSION CLOSE] Advance orders found: %d", len(advance_orders))
        _logger.info("[ADVANCE SESSION CLOSE] Completion orders found: %d", len(completion_orders))
        if advance_orders:
            for order in advance_orders:
                _logger.info("[ADVANCE SESSION CLOSE]   - Advance Order: %s (ID: %d) - Amount: %.2f - State: %s",
                            order.name, order.id, order.amount_total, order.state)
        if completion_orders:
            for order in completion_orders:
                _logger.info("[ADVANCE SESSION CLOSE]   - Completion Order: %s (ID: %d) - Amount: %.2f - State: %s - Advance Payment ID: %d",
                            order.name, order.id, order.amount_total, order.state, order.advance_payment_id.id)
        
        # Create account move (same as base)
        account_move = self.env['account.move'].create({
            'journal_id': self.config_id.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': self.name,
        })
        self.write({'move_id': account_move.id})
        _logger.info("[ADVANCE SESSION CLOSE] Account Move created - ID: %d", account_move.id)

        # Accumulate amounts (advance and completion payments are skipped - already recorded)
        data = {'bank_payment_method_diffs': bank_payment_method_diffs or {}}
        data = self._accumulate_amounts(data)
        
        # Create regular move lines
        data = self._create_non_reconciliable_move_lines(data)
        data = self._create_bank_payment_moves(data)
        data = self._create_pay_later_receivable_lines(data)
        data = self._create_cash_statement_lines_and_cash_move_lines(data)
        data = self._create_invoice_receivable_lines(data)
        data = self._create_stock_valuation_lines(data)
        
        # NOTE: Advance and completion payments are NOT processed here
        # - Advance payments: Already recorded via account.payment when advance order is created
        #   (with Debit: Cash/Bank, Credit: Advance Account)
        # - Completion payments: Already handled by Completion Move in action_create_invoice()
        #   (Completion Move records: Debit Cash/Bank + Advance Account, Credit Receivable)
        # No additional journal entries needed during session closing
        _logger.info("[ADVANCE SESSION CLOSE] Advance payments skipped - already recorded via account.payment")
        
        # Create balancing line if needed
        if balancing_account and amount_to_balance:
            data = self._create_balancing_line(data, balancing_account, amount_to_balance)
            _logger.info("[ADVANCE SESSION CLOSE] Balancing line created - Account: %s, Amount: %.2f",
                        balancing_account.name, amount_to_balance)

        # Log move balance status
        if self.move_id:
            move_balance = sum(self.move_id.line_ids.mapped('balance'))
            _logger.info("[ADVANCE SESSION CLOSE] Account Move created - ID: %d, Balance: %.2f", self.move_id.id, move_balance)
            
            # Check if balanced
            try:
                from odoo.exceptions import UserError
                with self.move_id._check_balanced({'records': self.move_id.sudo()}):
                    _logger.info("[ADVANCE SESSION CLOSE] ✓ Move is BALANCED")
            except UserError:
                _logger.error("[ADVANCE SESSION CLOSE] ⚠️⚠️⚠️ Move is UNBALANCED - Balance: %.2f ⚠️⚠️⚠️", move_balance)
                _logger.error("[ADVANCE SESSION CLOSE] This will trigger Force Close Session wizard")
                
                # Log all move lines for debugging
                _logger.error("[ADVANCE SESSION CLOSE] Move lines details:")
                for line in self.move_id.line_ids:
                    _logger.error("  - Account: %s | Debit: %.2f | Credit: %.2f | Balance: %.2f | Name: %s",
                                line.account_id.name, line.debit, line.credit, line.balance, line.name)

        return data
    
    def _create_bank_payment_moves(self, data):
        """
        Override to add logging and verify that advance payments are NOT processed
        """
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] _create_bank_payment_moves called for session: %s (ID: %d)", self.name, self.id)
        
        combine_receivables_bank = data.get('combine_receivables_bank', {})
        split_receivables_bank = data.get('split_receivables_bank', {})
        
        # Count advance and completion payments that should be skipped
        advance_orders = self.order_ids.filtered(lambda o: getattr(o, 'is_advance_order', False))
        completion_orders = self.order_ids.filtered(lambda o: o.advance_payment_id and not getattr(o, 'is_advance_order', False))
        advance_bank_payments = []
        completion_bank_payments = []
        for order in advance_orders:
            for payment in order.payment_ids:
                if payment.payment_method_id.type == 'bank':
                    advance_bank_payments.append(payment)
        for order in completion_orders:
            for payment in order.payment_ids:
                if payment.payment_method_id.type == 'bank':
                    completion_bank_payments.append(payment)
        
        _logger.info("[ADVANCE SESSION CLOSE] Bank payments processing:")
        _logger.info("  - Total combine_receivables_bank entries: %d", len(combine_receivables_bank))
        _logger.info("  - Total split_receivables_bank entries: %d", len(split_receivables_bank))
        _logger.info("  - Advance orders with bank payments: %d", len(advance_bank_payments))
        _logger.info("  - Completion orders with bank payments: %d", len(completion_bank_payments))
        
        all_advance_related_payments = advance_bank_payments + completion_bank_payments
        if all_advance_related_payments:
            _logger.info("[ADVANCE SESSION CLOSE] ✓ VERIFICATION: Advance/Completion bank payments should NOT be in receivables:")
            for payment in all_advance_related_payments:
                order_type = "Advance" if payment.pos_order_id in advance_orders else "Completion"
                is_in_combine = any(pm.id == payment.payment_method_id.id for pm in combine_receivables_bank.keys())
                is_in_split = payment in split_receivables_bank.keys()
                if is_in_combine or is_in_split:
                    _logger.error("[ADVANCE SESSION CLOSE] ⚠️ ERROR: %s payment found in receivables!", order_type)
                    _logger.error("  - Payment: %s (ID: %d), Amount: %.2f", payment.pos_order_id.name, payment.id, payment.amount)
                    _logger.error("  - In combine_receivables_bank: %s", is_in_combine)
                    _logger.error("  - In split_receivables_bank: %s", is_in_split)
                else:
                    _logger.info("  - ✓ %s payment skipped correctly: %s (ID: %d), Amount: %.2f", 
                                order_type, payment.pos_order_id.name, payment.id, payment.amount)
        else:
            _logger.info("[ADVANCE SESSION CLOSE] ✓ No advance/completion bank payments found - skipping verification")
        
        # Call parent method
        result = super()._create_bank_payment_moves(data)
        
        # Verify that no account.payment was created for advance or completion payments
        # Count account.payments created in this session
        account_payments_created = self.env['account.payment'].search([
            ('pos_session_id', '=', self.id),
            ('create_date', '>=', fields.Datetime.now() - timedelta(seconds=5)),  # Created in last 5 seconds
        ])
        advance_account_payments = account_payments_created.filtered(
            lambda p: p.pos_order_id and getattr(p.pos_order_id, 'is_advance_order', False)
        )
        completion_account_payments = account_payments_created.filtered(
            lambda p: p.pos_order_id and p.pos_order_id.advance_payment_id and not getattr(p.pos_order_id, 'is_advance_order', False)
        )
        
        all_advance_related_account_payments = advance_account_payments | completion_account_payments
        if all_advance_related_account_payments:
            _logger.error("[ADVANCE SESSION CLOSE] ⚠️ ERROR: account.payment was created for advance/completion payments during session closing!")
            for payment in advance_account_payments:
                _logger.error("  - account.payment ID: %d (Advance), Amount: %.2f, Order: %s", 
                             payment.id, payment.amount, payment.pos_order_id.name if payment.pos_order_id else "None")
            for payment in completion_account_payments:
                _logger.error("  - account.payment ID: %d (Completion), Amount: %.2f, Order: %s", 
                             payment.id, payment.amount, payment.pos_order_id.name if payment.pos_order_id else "None")
        else:
            _logger.info("[ADVANCE SESSION CLOSE] ✓ VERIFICATION: No account.payment created for advance/completion payments")
        
        _logger.info("[ADVANCE SESSION CLOSE] _create_bank_payment_moves completed")
        return result
    
    def _create_cash_statement_lines_and_cash_move_lines(self, data):
        """
        Override to add logging and verify that advance payments are NOT processed
        """
        _logger.info("[ADVANCE SESSION CLOSE] =========================================")
        _logger.info("[ADVANCE SESSION CLOSE] _create_cash_statement_lines_and_cash_move_lines called for session: %s (ID: %d)", self.name, self.id)
        
        combine_receivables_cash = data.get('combine_receivables_cash', {})
        split_receivables_cash = data.get('split_receivables_cash', {})
        
        # Count advance and completion payments that should be skipped
        advance_orders = self.order_ids.filtered(lambda o: getattr(o, 'is_advance_order', False))
        completion_orders = self.order_ids.filtered(lambda o: o.advance_payment_id and not getattr(o, 'is_advance_order', False))
        advance_cash_payments = []
        completion_cash_payments = []
        for order in advance_orders:
            for payment in order.payment_ids:
                if payment.payment_method_id.type == 'cash':
                    advance_cash_payments.append(payment)
        for order in completion_orders:
            for payment in order.payment_ids:
                if payment.payment_method_id.type == 'cash':
                    completion_cash_payments.append(payment)
        
        _logger.info("[ADVANCE SESSION CLOSE] Cash payments processing:")
        _logger.info("  - Total combine_receivables_cash entries: %d", len(combine_receivables_cash))
        _logger.info("  - Total split_receivables_cash entries: %d", len(split_receivables_cash))
        _logger.info("  - Advance orders with cash payments: %d", len(advance_cash_payments))
        _logger.info("  - Completion orders with cash payments: %d", len(completion_cash_payments))
        
        all_advance_related_payments = advance_cash_payments + completion_cash_payments
        if all_advance_related_payments:
            _logger.info("[ADVANCE SESSION CLOSE] ✓ VERIFICATION: Advance/Completion cash payments should NOT be in receivables:")
            for payment in all_advance_related_payments:
                order_type = "Advance" if payment.pos_order_id in advance_orders else "Completion"
                is_in_combine = any(pm.id == payment.payment_method_id.id for pm in combine_receivables_cash.keys())
                is_in_split = payment in split_receivables_cash.keys()
                if is_in_combine or is_in_split:
                    _logger.error("[ADVANCE SESSION CLOSE] ⚠️ ERROR: %s payment found in receivables!", order_type)
                    _logger.error("  - Payment: %s (ID: %d), Amount: %.2f", payment.pos_order_id.name, payment.id, payment.amount)
                    _logger.error("  - In combine_receivables_cash: %s", is_in_combine)
                    _logger.error("  - In split_receivables_cash: %s", is_in_split)
                else:
                    _logger.info("  - ✓ %s payment skipped correctly: %s (ID: %d), Amount: %.2f", 
                                order_type, payment.pos_order_id.name, payment.id, payment.amount)
        else:
            _logger.info("[ADVANCE SESSION CLOSE] ✓ No advance/completion cash payments found - skipping verification")
        
        # Call parent method
        result = super()._create_cash_statement_lines_and_cash_move_lines(data)
        
        # Verify that no account.payment or statement lines were created for advance or completion payments
        # Note: Cash payments create account.bank.statement.line, not account.payment
        # But we can verify by checking if any statement lines were created for advance/completion orders
        statement_lines_created = self.env['account.bank.statement.line'].search([
            ('pos_session_id', '=', self.id),
            ('create_date', '>=', fields.Datetime.now() - timedelta(seconds=5)),  # Created in last 5 seconds
        ])
        
        # Check if any statement lines are related to advance or completion orders
        advance_statement_lines = []
        completion_statement_lines = []
        for st_line in statement_lines_created:
            # Try to find related pos.payment and check if it's from advance/completion order
            pos_payments = self.env['pos.payment'].search([
                ('pos_order_id.session_id', '=', self.id),
                ('payment_date', '>=', st_line.date - timedelta(days=1)),
                ('payment_date', '<=', st_line.date + timedelta(days=1)),
            ])
            for pos_payment in pos_payments:
                if getattr(pos_payment.pos_order_id, 'is_advance_order', False) and abs(pos_payment.amount - abs(st_line.amount)) < 0.01:
                    advance_statement_lines.append(st_line)
                    break
                elif pos_payment.pos_order_id.advance_payment_id and not getattr(pos_payment.pos_order_id, 'is_advance_order', False) and abs(pos_payment.amount - abs(st_line.amount)) < 0.01:
                    completion_statement_lines.append(st_line)
                    break
        
        all_advance_related_statement_lines = advance_statement_lines + completion_statement_lines
        if all_advance_related_statement_lines:
            _logger.error("[ADVANCE SESSION CLOSE] ⚠️ ERROR: account.bank.statement.line was created for advance/completion payments during session closing!")
            for st_line in advance_statement_lines:
                _logger.error("  - Statement Line ID: %d (Advance), Amount: %.2f", st_line.id, st_line.amount)
            for st_line in completion_statement_lines:
                _logger.error("  - Statement Line ID: %d (Completion), Amount: %.2f", st_line.id, st_line.amount)
        else:
            _logger.info("[ADVANCE SESSION CLOSE] ✓ VERIFICATION: No account.bank.statement.line created for advance/completion payments")
        
        _logger.info("[ADVANCE SESSION CLOSE] _create_cash_statement_lines_and_cash_move_lines completed")
        return result

    # DEPRECATED: This function is no longer used
    # Advance payments are now recorded via account.payment when created
    # (with Debit: Cash/Bank, Credit: Advance Account)
    # No additional journal entries are needed during session closing
    # def _create_advance_payment_move_lines(self, data, advance_payments):
    #     """
    #     Create balanced accounting entry for advance payments:
    #     - Debit: Receivable (from payments)
    #     - Credit: Advance Account (liability)
    #     """
    #     ... REMOVED - No longer needed
