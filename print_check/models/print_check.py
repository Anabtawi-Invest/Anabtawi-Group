# -*- coding: utf-8 -*-
"""
Print Check Model
=================

Transient wizard model for printing bank cheques with customizable fields.
Extends account.payment with print_check action.
"""

from odoo import models, fields, api
from odoo.tools.misc import format_date
from datetime import date


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    is_check_payment = fields.Boolean(
        string='Check Payment',
        help='Payments using this method keep their Date set to today while in draft '
             'and use the Check Date field for the printed cheque.',
    )


class AccountPayment(models.Model):
    """Extend Account Payment to add Print Check action."""
    
    _inherit = 'account.payment'

    is_check_payment = fields.Boolean(related='payment_method_line_id.is_check_payment')
    check_date = fields.Date(string='Check Date', tracking=True, copy=False)
    check_number_confirmed = fields.Boolean(copy=False, readonly=True)
    check_manual_sequencing = fields.Boolean(
        related=None,
        compute='_compute_check_manual_sequencing',
    )

    @api.depends('journal_id.check_manual_sequencing', 'check_number_confirmed')
    @api.depends_context('keep_check_number')
    def _compute_check_manual_sequencing(self):
        keep = self.env.context.get('keep_check_number')
        for payment in self:
            payment.check_manual_sequencing = (
                payment.journal_id.check_manual_sequencing
                and not (keep and payment.check_number_confirmed)
            )

    @api.onchange('payment_method_line_id')
    def _onchange_check_payment_date(self):
        if self.is_check_payment and self.state == 'draft':
            self.date = fields.Date.context_today(self)
            if not self.check_date:
                self.check_date = self.date

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        method_lines = self.env['account.payment.method.line'].browse(
            [vals['payment_method_line_id'] for vals in vals_list if vals.get('payment_method_line_id')]
        )
        check_line_ids = set(method_lines.filtered('is_check_payment').ids)
        for vals in vals_list:
            if vals.get('payment_method_line_id') in check_line_ids:
                vals['check_date'] = vals.get('check_date') or vals.get('date') or today
                vals['date'] = today
        payments = super().create(vals_list)
        payments._force_check_payment_date()
        return payments

    def write(self, vals):
        moved = self.filtered(lambda p: p.check_number_confirmed and (
            ('journal_id' in vals and p.journal_id.id != vals['journal_id'])
            or ('payment_method_line_id' in vals
                and p.payment_method_line_id.id != vals['payment_method_line_id'])
        ))
        res = super().write(vals)
        if moved:
            moved.check_number_confirmed = False
        if not self.env.context.get('skip_check_payment_date'):
            self._force_check_payment_date()
        return res

    def action_post(self):
        self._force_check_payment_date()
        keep = self.filtered(
            lambda p: p.check_number_confirmed and p.check_number and p.state == 'draft'
        )
        if keep:
            super(AccountPayment, keep.with_context(keep_check_number=True)).action_post()
        rest = self - keep
        if rest:
            return super(AccountPayment, rest).action_post()

    def action_draft(self):
        self._confirm_issued_check_numbers()
        return super().action_draft()

    def action_cancel(self):
        self._confirm_issued_check_numbers()
        return super().action_cancel()

    def action_void_check(self):
        res = super().action_void_check()
        self.check_number_confirmed = False
        return res

    def _confirm_issued_check_numbers(self):
        self.filtered(
            lambda p: p.state in ('in_process', 'paid')
            and p.check_number
            and p.payment_method_code == 'check_printing'
            and p.journal_id.check_manual_sequencing
        ).check_number_confirmed = True

    def _force_check_payment_date(self):
        today = fields.Date.context_today(self)
        to_fix = self.filtered(
            lambda p: p.is_check_payment and p.state == 'draft' and p.date != today
        )
        if to_fix:
            to_fix.with_context(skip_check_payment_date=True).write({'date': today})

    def _get_cheque_memo(self):
        """Return memo/reference text for cheque printing (Odoo 19: memo, not ref)."""
        return self.memo or self.payment_reference or ''

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
            'cheque_date': self._format_cheque_date(self._get_cheque_print_date()),
            'currency_code': self.currency_id.name or 'JOD',
            'cheque_memo': self._get_cheque_memo(),
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
    
    def _get_cheque_print_date(self):
        if self.is_check_payment and self.check_date:
            return self.check_date
        return self.date or date.today()

    def _check_build_page_info(self, i, p):
        page = super()._check_build_page_info(i, p)
        page['date'] = format_date(self.env, self._get_cheque_print_date())
        return page

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
                    'cheque_date': self._format_date(payment._get_cheque_print_date()),
                    'currency_code': payment.currency_id.name or 'JOD',
                    'cheque_memo': payment._get_cheque_memo(),
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
