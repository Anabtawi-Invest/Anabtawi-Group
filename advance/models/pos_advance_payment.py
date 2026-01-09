from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PosAdvancePayment(models.Model):
    _name = 'pos.advance.payment'
    _description = 'POS Advance Payment'
    _order = 'create_date desc'

    name = fields.Char(
        string='Advance Number',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('New')
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True
    )

    total_expected = fields.Monetary(
        string='Total Expected Amount',
        required=True
    )

    amount_paid = fields.Monetary(
        string='Advance Amount',
        required=True
    )

    remaining_amount = fields.Monetary(
        string='Remaining Amount',
        compute='_compute_remaining_amount',
        store=True
    )

    payment_id = fields.Many2one(
        'account.payment',
        string='Advance Payment',
        readonly=True
    )
    payment_type = fields.Selection(
        [
            ('cash', 'Cash'),
            ('card', 'Card'),
        ],
        string='Payment Type',
        readonly=True
    )

    second_payment_id = fields.Many2one(
        'account.payment',
        string='Final Payment',
        readonly=True
    )

    # ✅ transfer entry that moves advance from liability to receivable
    transfer_move_id = fields.Many2one(
        'account.move',
        string='Advance Transfer Entry',
        readonly=True
    )

    invoice_id = fields.Many2one(
        'account.move',
        string='Final Invoice',
        readonly=True
    )

    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
        readonly=True
    )

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('paid', 'Paid'),
            ('invoiced', 'Invoiced'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True
    )

    note = fields.Text(string='Notes')

    line_ids = fields.One2many(
        "pos.advance.line",
        "advance_id",
        string="Advance Lines"
    )

    # --------------------------------------------------
    # COMPUTE
    # --------------------------------------------------
    @api.depends('total_expected', 'amount_paid')
    def _compute_remaining_amount(self):
        for record in self:
            record.remaining_amount = (record.total_expected or 0.0) - (record.amount_paid or 0.0)

    # --------------------------------------------------
    # SEQUENCE
    # --------------------------------------------------
    @api.model
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pos.advance.payment') or _('New')
        return super().create(vals_list)

    # --------------------------------------------------
    # CREATE ADVANCE FROM POS
    # --------------------------------------------------
    def _get_payment_journal(self):
        self.ensure_one()

        company = self.company_id

        if self.payment_type == 'cash':
            journal = company.pos_cash_journal_id
        elif self.payment_type == 'card':
            journal = company.pos_card_journal_id
        else:
            journal = False

        if not journal:
            raise ValidationError(_("Please configure journal for payment type: %s") % self.payment_type)

        return journal

    def _get_inbound_payment_method_line(self, journal):
        """
        Return first inbound payment method line of a journal
        """
        method_line = journal.inbound_payment_method_line_ids[:1]
        if not method_line:
            raise ValidationError(
                _("No inbound payment method line defined for journal: %s") % journal.display_name
            )
        return method_line

    @api.model
    def create_from_pos(self, vals):
        partner_id = vals.get('partner_id')
        amount_paid = vals.get('amount_paid')
        total_expected = vals.get('total_expected')
        lines = vals.get('lines', [])
        payment_type = vals.get('payment_type')

        # --------------------------------------------------
        # VALIDATION
        # --------------------------------------------------
        if not partner_id:
            raise ValidationError(_('Customer is required.'))

        if not amount_paid or amount_paid <= 0:
            raise ValidationError(_('Advance amount must be greater than zero.'))

        if amount_paid > total_expected:
            raise ValidationError(_('Advance amount cannot exceed total amount.'))

        if not lines:
            raise ValidationError(_('Advance must contain at least one product.'))

        if payment_type not in ('cash', 'card'):
            raise ValidationError(_('Invalid payment type.'))

        company = self.env.company

        if not company.pos_advance_account_id:
            raise ValidationError(_('Please configure POS Advance Account in Settings.'))

        # --------------------------------------------------
        # SELECT JOURNAL BY PAYMENT TYPE
        # --------------------------------------------------
        if payment_type == 'cash':
            journal = company.pos_cash_journal_id
            if not journal:
                raise ValidationError(_('Please configure POS Cash Journal.'))
        else:
            journal = company.pos_card_journal_id
            if not journal:
                raise ValidationError(_('Please configure POS Card Journal.'))

        # --------------------------------------------------
        # 1) CREATE ADVANCE HEADER
        # --------------------------------------------------
        advance = self.sudo().create({
            'partner_id': partner_id,
            'amount_paid': amount_paid,
            'total_expected': total_expected,
            'company_id': company.id,
            'payment_type': payment_type,
        })

        # --------------------------------------------------
        # 2) CREATE ADVANCE LINES
        # --------------------------------------------------
        for line in lines:
            self.env['pos.advance.line'].sudo().create({
                'advance_id': advance.id,
                'product_id': line['product_id'],
                'qty': line['qty'],
                'price_unit': line['price_unit'],
            })

        # --------------------------------------------------
        # 3) FIND PAYMENT METHOD LINE (🔥 CRITICAL)
        # --------------------------------------------------
        payment_method_line = journal.inbound_payment_method_line_ids[:1]
        if not payment_method_line:
            raise ValidationError(
                _('Please define an inbound payment method on journal %s.')
                % journal.display_name
            )

        # --------------------------------------------------
        # 4) CREATE PAYMENT (LIABILITY)
        # --------------------------------------------------
        payment = self.env['account.payment'].sudo().create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner_id,
            'amount': amount_paid,
            'currency_id': company.currency_id.id,
            'journal_id': journal.id,
            'payment_method_line_id': payment_method_line.id,  # ✅ FIX
            'date': fields.Date.context_today(self),
            'memo': advance.name,
            'destination_account_id': company.pos_advance_account_id.id,  # liability
        })
        payment.action_post()

        # --------------------------------------------------
        # 5) MARK ADVANCE AS PAID
        # --------------------------------------------------
        advance.write({
            'payment_id': payment.id,
            'state': 'paid',
        })

        return {
            'id': advance.id,
            'name': advance.name,
        }

    def _create_advance_transfer_move(self, invoice):
        self.ensure_one()

        partner = self.partner_id
        company = self.company_id

        receivable_account = partner.property_account_receivable_id
        advance_account = company.pos_advance_account_id

        move = self.env['account.move'].sudo().create({
            'move_type': 'entry',
            'date': invoice.invoice_date or fields.Date.context_today(self),
            'ref': self.name,
            'company_id': company.id,
            'line_ids': [
                # 🔴 Credit Receivable (reduce customer debt)
                (0, 0, {
                    'name': _('Apply POS Advance %s') % self.name,
                    'partner_id': partner.id,
                    'account_id': receivable_account.id,
                    'debit': 0.0,
                    'credit': self.amount_paid,
                }),
                # 🟢 Debit Advance Liability (close advance)
                (0, 0, {
                    'name': _('Apply POS Advance %s') % self.name,
                    'partner_id': partner.id,
                    'account_id': advance_account.id,
                    'debit': self.amount_paid,
                    'credit': 0.0,
                }),
            ],
        })

        move.action_post()
        self.transfer_move_id = move.id
        return move

    # --------------------------------------------------
    # CREATE INVOICE + APPLY ADVANCE + RECONCILE
    # --------------------------------------------------
    def action_create_invoice(self, vals=None):
        payment_type = (vals or {}).get('payment_type')

        for advance in self:
            if payment_type:
                advance.payment_type = payment_type
            if advance.invoice_id:
                raise ValidationError(_("Invoice already created."))

            if not advance.line_ids:
                raise ValidationError(_("No products to invoice."))

            company = advance.company_id
            partner = advance.partner_id

            if not advance.payment_id:
                raise ValidationError(_("Advance payment not found."))

            # 1) (Optional) Create final payment for remaining amount
            if not advance.second_payment_id and advance.remaining_amount > 0:
                if not company.second_journal_id:
                    raise ValidationError(_("Please configure POS Journal (second_journal_id) in Settings."))

            # 2) Create invoice (full amount)
            invoice_lines = [
                (0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.qty,
                    'price_unit': line.price_unit,
                    'name': line.product_id.display_name,
                })
                for line in advance.line_ids
            ]

            invoice = advance.env['account.move'].sudo().create({
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'invoice_date': fields.Date.context_today(advance),
                'invoice_line_ids': invoice_lines,
                'company_id': company.id,
            })
            invoice.action_post()

            # 3) Create transfer entry to move advance from liability -> receivable
            transfer_move = advance._create_advance_transfer_move(invoice)

            # 4) Reconcile receivable lines (Invoice + Transfer + Second Payment)
            moves = invoice | transfer_move
            if advance.second_payment_id and advance.second_payment_id.move_id:
                moves |= advance.second_payment_id.move_id

            receivable_lines = moves.line_ids.filtered(
                lambda l: l.account_type == 'asset_receivable' and not l.reconciled
            )

            print("--- RECEIVABLE LINES BEFORE ---")
            for l in receivable_lines:
                print("Line", l.id, "| Move:", l.move_id.name, "| Debit:", l.debit, "| Credit:", l.credit,
                      "| Reconciled:", l.reconciled)

            if receivable_lines:
                receivable_lines.reconcile()

            print("--- RECEIVABLE LINES AFTER ---")
            for l in moves.line_ids.filtered(lambda l: l.account_type == 'asset_receivable'):
                print("Line", l.id, "| Move:", l.move_id.name, "| Reconciled:", l.reconciled,
                      "| Matched Debits:", l.matched_debit_ids.ids, "| Matched Credits:", l.matched_credit_ids.ids)

            # 5) Mark invoiced
            advance.write({
                'invoice_id': invoice.id,
                'state': 'invoiced',
            })

            if advance.remaining_amount > 0:
                journal = advance._get_payment_journal()

                wizard = self.env['account.payment.register'].with_context(
                    active_model='account.move',
                    active_ids=invoice.ids,
                ).create({
                    'journal_id': journal.id,  # 👈 cash / card
                    'amount': advance.remaining_amount,
                    'payment_date': fields.Date.context_today(self),
                })

                payments = wizard._create_payments()
                advance.second_payment_id = payments.id

            advance.write({
                'invoice_id': invoice.id,
                'state': 'invoiced',
            })
            invoice.write({
                'state': 'paid'
            })
            return invoice

    def action_mark_invoiced(self, invoice):
        self.write({'invoice_id': invoice.id, 'state': 'invoiced'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})


class PosAdvanceLine(models.Model):
    _name = "pos.advance.line"
    _description = "POS Advance Line"

    advance_id = fields.Many2one(
        "pos.advance.payment",
        required=True,
        ondelete="cascade"
    )

    product_id = fields.Many2one(
        "product.product",
        required=True
    )

    qty = fields.Float(required=True)
    price_unit = fields.Float(required=True)

    subtotal = fields.Monetary(
        compute="_compute_subtotal",
        store=True
    )

    currency_id = fields.Many2one(
        related="advance_id.currency_id",
        store=True
    )

    @api.depends("qty", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.price_unit
