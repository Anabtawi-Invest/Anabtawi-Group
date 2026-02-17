# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.tools import float_is_zero
import logging

_logger = logging.getLogger(__name__)


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    def _create_payment_moves(self, is_reverse=False):
        print(33333)
        """
        Override to prevent Payment Move creation for Advance Orders.
        
        For Advance Orders:
        - We keep pos.payment records (for closing session reports) ✅
        - But we don't create Payment Move (to avoid duplication) ✅
        - Completion Move handles the accounting instead ✅
        
        This prevents the duplicate Account Receivable entries that occur when:
        1. Odoo's standard _generate_pos_order_invoice() calls _create_payment_moves()
        2. Our custom action_create_invoice() creates Completion Move
        
        Without this override, both moves would Credit Account Receivable, causing:
        - Account Receivable to show negative balance (Credit > Debit)
        - Incorrect Balance Sheet reporting
        """
        # Filter out payments from Advance Orders
        # Check if pos_order_id is linked to an advance_payment_id or is_advance_order
        advance_payments = self.filtered(
            lambda p: p.pos_order_id.advance_payment_id or 
                     getattr(p.pos_order_id, 'is_advance_order', False)
        )
        regular_payments = self - advance_payments
        
        if advance_payments:
            _logger.info(
                "[ADVANCE PAYMENT] Filtering out %d advance payment(s) from Payment Move creation. "
                "Completion Move will handle accounting instead.",
                len(advance_payments)
            )
            for payment in advance_payments:
                _logger.info(
                    "[ADVANCE PAYMENT] Skipping Payment Move for pos.payment ID %d "
                    "(Order: %s, Amount: %.2f)",
                    payment.id, payment.pos_order_id.name, payment.amount
                )
        
        # Only create Payment Moves for regular (non-advance) payments
        if regular_payments:
            return super(PosPayment, regular_payments)._create_payment_moves(is_reverse=is_reverse)
        
        # Return empty recordset if all payments are advance payments
        return self.env['account.move']
