# -*- coding: utf-8 -*-
"""
Print Check Model
=================

Transient wizard model for printing bank cheques with customizable fields.
Extends account.payment with print_check action.
"""

from odoo import models, fields, api
from datetime import date


class AccountPayment(models.Model):
    """Extend Account Payment to add Print Check action."""
    
    _inherit = 'account.payment'

    def action_print_check(self):
        """
        Open the Print Check wizard for the current payment.
        
        Creates a transient print.check record with data from this payment
        and opens the form view in current window.
        """
        self.ensure_one()
        
        # Create the print check wizard with payment data
        print_check = self.env['print.check'].create({
            'payment_id': self.id,
            'partner_id': self.partner_id.id,
            'partner_name': self.partner_id.name or '',
            'cheque_amount': self.amount,
            'cheque_date': self._format_cheque_date(self.date or date.today()),
            'currency_code': self.currency_id.name or 'JOD',
            'cheque_memo': self.ref or '',
        })
        
        return {
            'name': 'Print Cheque / طباعة شيك',
            'type': 'ir.actions.act_window',
            'res_model': 'print.check',
            'res_id': print_check.id,
            'view_mode': 'form',
            'target': 'current',
            'context': self.env.context,
        }
    
    def _format_cheque_date(self, dt):
        """Format date for cheque display (DD/MM/YYYY)."""
        if not dt:
            return ''
        if isinstance(dt, str):
            return dt
        return dt.strftime('%d/%m/%Y')


class PrintCheck(models.TransientModel):
    """
    Transient model for the Print Check wizard.
    
    Stores all the data needed for cheque printing in a temporary record.
    The actual UI is rendered via custom HTML in the form view,
    with JavaScript handling all the interactive features.
    """
    
    _name = 'print.check'
    _description = 'Print Check Wizard'

    # Link fields
    payment_id = fields.Many2one('account.payment', string='Payment', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    
    # Display fields (passed to JavaScript)
    partner_name = fields.Char(string='Payee Name')
    cheque_date = fields.Char(string='Cheque Date')
    cheque_amount = fields.Float(string='Amount', digits=(16, 3))
    currency_code = fields.Char(string='Currency Code')
    cheque_memo = fields.Char(string='Memo')
    
    @api.model
    def default_get(self, fields_list):
        """
        Override default_get to populate fields from context.
        
        Handles two sources:
        1. account.payment (standard Accounting payments)
        2. pdc.wizard (PDC module - passes defaults directly in context)
        """
        res = super().default_get(fields_list)
        
        # Check if we have a payment in context (from account.payment)
        payment_id = self._context.get('active_id')
        payment_model = self._context.get('active_model')
        
        if payment_id and payment_model == 'account.payment':
            payment = self.env['account.payment'].browse(payment_id)
            if payment.exists():
                res.update({
                    'payment_id': payment.id,
                    'partner_id': payment.partner_id.id,
                    'partner_name': payment.partner_id.name or '',
                    'cheque_amount': payment.amount,
                    'cheque_date': self._format_date(payment.date),
                    'currency_code': payment.currency_id.name or 'JOD',
                    'cheque_memo': payment.ref or '',
                })
        
        # Handle PDC wizard context (already passes default_ prefixed values)
        # The context already sets default_partner_name, default_cheque_amount, etc.
        # But we need to handle the date formatting
        if self._context.get('default_cheque_date'):
            cheque_date = self._context.get('default_cheque_date')
            # If it's a date object, format it
            if hasattr(cheque_date, 'strftime'):
                res['cheque_date'] = cheque_date.strftime('%d/%m/%Y')
            elif isinstance(cheque_date, str):
                res['cheque_date'] = cheque_date
        
        # Use formatted date if provided
        if self._context.get('default_cheque_date_formatted'):
            res['cheque_date'] = self._context.get('default_cheque_date_formatted')
        
        # Default currency if not set
        if not res.get('currency_code'):
            res['currency_code'] = 'JOD'
        
        return res
    
    def _format_date(self, dt):
        """Format date for cheque display (DD/MM/YYYY)."""
        if not dt:
            return date.today().strftime('%d/%m/%Y')
        if isinstance(dt, str):
            return dt
        return dt.strftime('%d/%m/%Y')
