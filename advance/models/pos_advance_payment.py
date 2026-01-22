from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class PosAdvancePayment(models.Model):
    _name = 'pos.advance.payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
        readonly=True,
        help='Main payment (for single payment type). For mixed payments, see cash_payment_id and card_payment_id.'
    )

    cash_payment_id = fields.Many2one(
        'account.payment',
        string='Cash Payment',
        readonly=True,
        help='Cash payment (for mixed payments)'
    )

    card_payment_id = fields.Many2one(
        'account.payment',
        string='Card Payment',
        readonly=True,
        help='Card payment (for mixed payments)'
    )
    payment_type = fields.Selection(
        [
            ('cash', 'Cash'),
            ('card', 'Card'),
            ('mixed', 'Mixed (Cash & Card)'),
        ],
        string='Payment Type',
        readonly=True
    )

    cash_amount = fields.Monetary(
        string='Cash Amount',
        help='Amount paid in cash (for mixed payments)',
        default=0.0
    )

    card_amount = fields.Monetary(
        string='Card Amount',
        help='Amount paid by card (for mixed payments)',
        default=0.0
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
    completion_move_id = fields.Many2one(
        'account.move',
        string='Completion Journal Entry',
        readonly=True
    )

    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
        readonly=True
    )

    pos_config_id = fields.Many2one(
        'pos.config',
        string='POS Configuration',
        required=True
    )

    pickup_pos_id = fields.Many2one(
        'pos.config',
        string='Pickup Location (POS)',
        help="Point of Sale where the order will be collected"
    )

    due_date = fields.Date(
        string='Due Date',
        help="Expected date for order completion/pickup"
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

        pos_config = self.pos_config_id

        if self.payment_type == 'cash':
            journal = pos_config.pos_cash_journal_id
        elif self.payment_type == 'card':
            journal = pos_config.pos_card_journal_id
        elif self.payment_type == 'mixed':
            # For mixed payment, return cash journal as primary (for backward compatibility)
            journal = pos_config.pos_cash_journal_id or pos_config.pos_card_journal_id
        else:
            journal = False

        if not journal:
            raise ValidationError(
                _("Please configure %s journal in POS Configuration: %s") % (self.payment_type or 'payment',
                                                                             pos_config.name))

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

        return pos_payment_method

    def _create_pos_order_for_advance(self, pos_session, partner, pos_config, employee_id=False):
        """
        Create a minimal pos.order for advance payment
        """
        # Create a dummy order line (required by pos.order)
        dummy_product = self.env['product.product'].search([
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True),
        ], limit=1)

        if not dummy_product:
            raise ValidationError(_('No product available for POS. Please create at least one product.'))

        # Generate unique pos_reference for advance order
        # Use prefix "ADV-" to distinguish from regular orders
        pos_reference, tracking_number = pos_config._get_next_order_refs()
        # Add "ADV-" prefix to make it unique
        pos_reference = f"ADV-{pos_reference}"

        pos_order_vals = {
            'session_id': pos_session.id,
            'partner_id': partner.id,
            'config_id': pos_config.id,
            'company_id': pos_config.company_id.id,
            'pricelist_id': partner.property_product_pricelist.id or pos_config.pricelist_id.id,
            'pos_reference': pos_reference,  # Set pos_reference explicitly to avoid duplicate
            'tracking_number': tracking_number,
            'lines': [(0, 0, {
                'product_id': dummy_product.id,
                'qty': 0,  # Zero quantity
                'price_unit': 0.0,
                'price_subtotal': 0.0,
                'price_subtotal_incl': 0.0,
            })],
            'amount_total': 0.0,
            'amount_tax': 0.0,
            'amount_paid': 0.0,
            'amount_return': 0.0,
            'advance_payment_id': self.id,
            'is_advance_order': True,
        }

        if employee_id:
            pos_order_vals['employee_id'] = employee_id

        pos_order = self.env['pos.order'].sudo().create(pos_order_vals)
        return pos_order

    @api.model
    def create_from_pos(self, vals):
        print(655466644)
        _logger.info("[ADVANCE CREATE] =========================================")
        _logger.info("[ADVANCE CREATE] create_from_pos called with vals: %s", vals)
        partner_id = vals.get('partner_id')
        amount_paid = vals.get('amount_paid')
        total_expected = vals.get('total_expected')
        lines = vals.get('lines', [])
        payment_type = vals.get('payment_type')
        pos_config_id = vals.get('pos_config_id')
        pickup_pos_id = vals.get('pickup_pos_id')
        due_date = vals.get('due_date')
        _logger.info("[ADVANCE CREATE] Amount Paid: %.2f, Payment Type: %s", amount_paid, payment_type)

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

        if payment_type not in ('cash', 'card', 'mixed'):
            raise ValidationError(_('Invalid payment type.'))

        # For mixed payment, validate cash_amount and card_amount
        cash_amount = vals.get('cash_amount', 0.0) or 0.0
        card_amount = vals.get('card_amount', 0.0) or 0.0

        if payment_type == 'mixed':
            if cash_amount <= 0 and card_amount <= 0:
                raise ValidationError(
                    _('For mixed payment, at least one amount (cash or card) must be greater than zero.'))
            if cash_amount + card_amount != amount_paid:
                raise ValidationError(_('Cash amount + Card amount must equal total amount paid.'))
        elif payment_type == 'cash':
            cash_amount = amount_paid
            card_amount = 0.0
        elif payment_type == 'card':
            cash_amount = 0.0
            card_amount = amount_paid

        if not pos_config_id:
            raise ValidationError(_('POS Configuration is required.'))

        pos_config = self.env['pos.config'].browse(pos_config_id)
        company = pos_config.company_id

        if not pos_config.pos_advance_account_id:
            raise ValidationError(_('Please configure POS Advance Account in POS Configuration: %s') % pos_config.name)

        # --------------------------------------------------
        # SELECT JOURNAL BY PAYMENT TYPE
        # --------------------------------------------------
        cash_journal = None
        card_journal = None

        if payment_type in ('cash', 'mixed'):
            cash_journal = pos_config.pos_cash_journal_id
            if payment_type == 'cash' and not cash_journal:
                raise ValidationError(_('Please configure POS Cash Journal in POS Configuration: %s') % pos_config.name)
            if payment_type == 'mixed' and cash_amount > 0 and not cash_journal:
                raise ValidationError(_('Please configure POS Cash Journal in POS Configuration: %s') % pos_config.name)

        if payment_type in ('card', 'mixed'):
            card_journal = pos_config.pos_card_journal_id
            if payment_type == 'card' and not card_journal:
                raise ValidationError(_('Please configure POS Card Journal in POS Configuration: %s') % pos_config.name)
            if payment_type == 'mixed' and card_amount > 0 and not card_journal:
                raise ValidationError(_('Please configure POS Card Journal in POS Configuration: %s') % pos_config.name)

        # For single payment type, set journal variable for backward compatibility
        if payment_type == 'cash':
            journal = cash_journal
        elif payment_type == 'card':
            journal = card_journal
        else:
            journal = None  # Will not be used for mixed payment

        # --------------------------------------------------
        # 1) CREATE ADVANCE HEADER
        # --------------------------------------------------
        advance = self.sudo().create({
            'partner_id': partner_id,
            'amount_paid': amount_paid,
            'total_expected': total_expected,
            'company_id': company.id,
            'payment_type': payment_type,
            'cash_amount': cash_amount,
            'card_amount': card_amount,
            'pos_config_id': pos_config_id,
            'pickup_pos_id': pickup_pos_id or pos_config_id,  # Default to current POS if not specified
            'due_date': due_date,
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
        # 3) GET POS SESSION AND CREATE POS ORDER
        # --------------------------------------------------
        pos_session = self.env['pos.session'].search([
            ('state', '=', 'opened'),
            ('config_id', '=', pos_config_id),
            ('company_id', '=', company.id),
        ], limit=1)

        if not pos_session:
            raise ValidationError(_("No open POS session found. Please open a POS session first."))

        # Get partner record
        partner = self.env['res.partner'].browse(partner_id)

        # Create pos.order for advance
        pos_order = advance._create_pos_order_for_advance(
            pos_session,
            partner,
            pos_config,
            employee_id=False
        )

        # --------------------------------------------------
        # 4) CREATE POS.PAYMENT(S) AND ACCOUNT.PAYMENT(S)
        # --------------------------------------------------
        cash_payment = None
        card_payment = None
        main_payment = None
        cash_pos_payment = None
        card_pos_payment = None
        main_pos_payment = None

        if payment_type == 'mixed':
            # Create two separate payments for mixed payment
            if cash_amount > 0:

                # Get pos.payment.method for cash journal
                cash_pos_payment_method = advance._get_pos_payment_method_from_journal(cash_journal, pos_config)
                
                # Verify that payment method is linked to this POS config only
                # If it's linked to another config, don't set pos_payment_method_id to avoid constraint error
                can_use_payment_method = True
                if cash_pos_payment_method:
                    other_configs = self.env['pos.config'].search([
                        ('payment_method_ids', 'in', [cash_pos_payment_method.id]),
                        ('id', '!=', pos_config.id),
                    ])
                    if other_configs:
                        _logger.warning("[ADVANCE PAYMENT] Cash payment method %s (ID: %d) is linked to other POS configs: %s. Not setting pos_payment_method_id to avoid constraint error.",
                                       cash_pos_payment_method.name, cash_pos_payment_method.id, other_configs.mapped('name'))
                        can_use_payment_method = False

                # Create account.payment
                cash_payment_method_line = cash_journal.inbound_payment_method_line_ids[:1]
                if not cash_payment_method_line:
                    raise ValidationError(
                        _('Please define an inbound payment method on cash journal %s.')
                        % cash_journal.display_name
                    )
                _logger.info("[ADVANCE PAYMENT] =========================================")
                _logger.info("[ADVANCE PAYMENT] Creating cash payment for advance %s", advance.name)
                _logger.info("[ADVANCE PAYMENT] Amount: %.2f, Destination Account: %s (ID: %d)",
                             cash_amount, pos_config.pos_advance_account_id.name, pos_config.pos_advance_account_id.id)
                _logger.info("[ADVANCE PAYMENT] Payment Method Line: %s, Payment Account: %s",
                             cash_payment_method_line.name,
                             cash_payment_method_line.payment_account_id.name if cash_payment_method_line.payment_account_id else "None")
                
                payment_vals = {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': partner_id,
                    'amount': cash_amount,
                    'currency_id': company.currency_id.id,
                    'journal_id': cash_journal.id,
                    'payment_method_line_id': cash_payment_method_line.id,
                    'date': fields.Date.context_today(self),
                    'memo': _('%s (Cash)') % advance.name,
                    'destination_account_id': pos_config.pos_advance_account_id.id,
                    'pos_session_id': pos_session.id,
                }
                # Only set pos_payment_method_id if it's safe (not linked to other configs)
                if can_use_payment_method and cash_pos_payment_method:
                    payment_vals['pos_payment_method_id'] = cash_pos_payment_method.id
                
                _logger.info("[ADVANCE PAYMENT] About to create account.payment for cash payment:")
                _logger.info("  - Amount: %.2f", cash_amount)
                _logger.info("  - Partner: %s (ID: %d)", partner.name, partner_id)
                _logger.info("  - Journal: %s (ID: %d)", cash_journal.name, cash_journal.id)
                _logger.info("  - Destination Account: %s (ID: %d)", pos_config.pos_advance_account_id.name, pos_config.pos_advance_account_id.id)
                
                # Count existing payments before creation
                existing_payments_before = self.env['account.payment'].search_count([
                    ('partner_id', '=', partner_id),
                    ('amount', '=', cash_amount),
                    ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=1)),
                ])
                _logger.info("[ADVANCE PAYMENT] Existing payments with same amount (last minute): %d", existing_payments_before)
                
                cash_payment = self.env['account.payment'].sudo().create(payment_vals)
                _logger.info("[ADVANCE PAYMENT] ✓ Created account.payment - ID: %d, Name: %s, Amount: %.2f", 
                            cash_payment.id, cash_payment.name, cash_payment.amount)
                
                # Count existing payments after creation
                existing_payments_after = self.env['account.payment'].search_count([
                    ('partner_id', '=', partner_id),
                    ('amount', '=', cash_amount),
                    ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=1)),
                ])
                _logger.info("[ADVANCE PAYMENT] Total payments with same amount (last minute): %d", existing_payments_after)
                
                # Flush to ensure computed fields are updated
                cash_payment.flush_recordset(['outstanding_account_id', 'destination_account_id'])

                # Set outstanding_account_id to Cash/Bank (journal.default_account_id) directly
                # This ensures advance payment is posted to Cash/Bank, not Outstanding Receipts
                if cash_journal and cash_journal.default_account_id:
                    cash_payment.outstanding_account_id = cash_journal.default_account_id.id
                    cash_payment.flush_recordset(['outstanding_account_id'])
                    _logger.info("[ADVANCE PAYMENT] Set outstanding_account_id to Cash/Bank: %s (ID: %d)",
                                 cash_journal.default_account_id.name, cash_journal.default_account_id.id)
                elif not cash_payment.outstanding_account_id:
                    # Fallback: get outstanding account from journal/company (should not happen)
                    outstanding_account = cash_payment._get_outstanding_account(cash_payment.payment_type)
                    cash_payment.outstanding_account_id = outstanding_account.id
                    cash_payment.flush_recordset(['outstanding_account_id'])
                    _logger.warning("[ADVANCE PAYMENT] Using fallback outstanding account: %s (ID: %d)",
                                    outstanding_account.name, outstanding_account.id)

                _logger.info(
                    "[ADVANCE PAYMENT] Cash payment created - ID: %d, State: %s, Outstanding Account: %s (ID: %s), Destination Account: %s (ID: %s)",
                    cash_payment.id, cash_payment.state,
                    cash_payment.outstanding_account_id.name if cash_payment.outstanding_account_id else "None",
                    cash_payment.outstanding_account_id.id if cash_payment.outstanding_account_id else "None",
                    cash_payment.destination_account_id.name if cash_payment.destination_account_id else "None",
                    cash_payment.destination_account_id.id if cash_payment.destination_account_id else "None")

                # Generate journal entry explicitly to ensure account.move.line are created
                if cash_payment.outstanding_account_id:
                    cash_payment._generate_journal_entry()
                    _logger.info("[ADVANCE PAYMENT] Journal entry generated for cash payment")
                else:
                    _logger.warning(
                        "[ADVANCE PAYMENT] Cannot generate journal entry: outstanding_account_id is missing!")

                # Post the payment (this will also post the journal entry if it's draft)
                cash_payment.action_post()
                _logger.info("[ADVANCE PAYMENT] Cash payment posted - ID: %d, State: %s, Move ID: %s",
                             cash_payment.id, cash_payment.state,
                             cash_payment.move_id.id if cash_payment.move_id else "None")
                if cash_payment.move_id:
                    _logger.info("[ADVANCE PAYMENT] Cash payment move - ID: %d, State: %s",
                                 cash_payment.move_id.id, cash_payment.move_id.state)
                    for line in cash_payment.move_id.line_ids:
                        _logger.info("[ADVANCE PAYMENT]   - Line: Account=%s (ID: %d), Debit=%.2f, Credit=%.2f",
                                     line.account_id.name, line.account_id.id, line.debit, line.credit)
                else:
                    _logger.warning("[ADVANCE PAYMENT] Cash payment has no move_id after action_post()!")

                # Create pos.payment
                cash_pos_payment = self.env['pos.payment'].sudo().create({
                    'pos_order_id': pos_order.id,
                    'payment_method_id': cash_pos_payment_method.id,
                    'amount': cash_amount,
                    'payment_date': fields.Datetime.now(),
                })

            if card_amount > 0:
                # Get pos.payment.method for card journal
                card_pos_payment_method = advance._get_pos_payment_method_from_journal(card_journal, pos_config)
                
                # Verify that payment method is linked to this POS config only
                # If it's linked to another config, don't set pos_payment_method_id to avoid constraint error
                can_use_payment_method = True
                if card_pos_payment_method:
                    other_configs = self.env['pos.config'].search([
                        ('payment_method_ids', 'in', [card_pos_payment_method.id]),
                        ('id', '!=', pos_config.id),
                    ])
                    if other_configs:
                        _logger.warning("[ADVANCE PAYMENT] Card payment method %s (ID: %d) is linked to other POS configs: %s. Not setting pos_payment_method_id to avoid constraint error.",
                                       card_pos_payment_method.name, card_pos_payment_method.id, other_configs.mapped('name'))
                        can_use_payment_method = False

                # Create account.payment
                card_payment_method_line = card_journal.inbound_payment_method_line_ids[:1]
                if not card_payment_method_line:
                    raise ValidationError(
                        _('Please define an inbound payment method on card journal %s.')
                        % card_journal.display_name
                    )
                _logger.info("[ADVANCE PAYMENT] =========================================")
                _logger.info("[ADVANCE PAYMENT] Creating card payment for advance %s", advance.name)
                _logger.info("[ADVANCE PAYMENT] Amount: %.2f, Destination Account: %s (ID: %d)",
                             card_amount, pos_config.pos_advance_account_id.name, pos_config.pos_advance_account_id.id)
                _logger.info("[ADVANCE PAYMENT] Payment Method Line: %s, Payment Account: %s",
                             card_payment_method_line.name,
                             card_payment_method_line.payment_account_id.name if card_payment_method_line.payment_account_id else "None")
                
                payment_vals = {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': partner_id,
                    'amount': card_amount,
                    'currency_id': company.currency_id.id,
                    'journal_id': card_journal.id,
                    'payment_method_line_id': card_payment_method_line.id,
                    'date': fields.Date.context_today(self),
                    'memo': _('%s (Card)') % advance.name,
                    'destination_account_id': pos_config.pos_advance_account_id.id,
                    'pos_session_id': pos_session.id,
                }
                # Only set pos_payment_method_id if it's safe (not linked to other configs)
                if can_use_payment_method and card_pos_payment_method:
                    payment_vals['pos_payment_method_id'] = card_pos_payment_method.id
                
                card_payment = self.env['account.payment'].sudo().create(payment_vals)
                # Flush to ensure computed fields are updated
                card_payment.flush_recordset(['outstanding_account_id', 'destination_account_id'])

                # Set outstanding_account_id to Card Account (journal.default_account_id) directly
                # This ensures advance payment is posted to Card Account, not Outstanding Receipts
                if card_journal and card_journal.default_account_id:
                    card_payment.outstanding_account_id = card_journal.default_account_id.id
                    card_payment.flush_recordset(['outstanding_account_id'])
                    _logger.info("[ADVANCE PAYMENT] Set outstanding_account_id to Card Account: %s (ID: %d)",
                                 card_journal.default_account_id.name, card_journal.default_account_id.id)
                elif not card_payment.outstanding_account_id:
                    # Fallback: get outstanding account from journal/company (should not happen)
                    outstanding_account = card_payment._get_outstanding_account(card_payment.payment_type)
                    card_payment.outstanding_account_id = outstanding_account.id
                    card_payment.flush_recordset(['outstanding_account_id'])
                    _logger.warning("[ADVANCE PAYMENT] Using fallback outstanding account: %s (ID: %d)",
                                    outstanding_account.name, outstanding_account.id)

                _logger.info(
                    "[ADVANCE PAYMENT] Card payment created - ID: %d, State: %s, Outstanding Account: %s (ID: %s), Destination Account: %s (ID: %s)",
                    card_payment.id, card_payment.state,
                    card_payment.outstanding_account_id.name if card_payment.outstanding_account_id else "None",
                    card_payment.outstanding_account_id.id if card_payment.outstanding_account_id else "None",
                    card_payment.destination_account_id.name if card_payment.destination_account_id else "None",
                    card_payment.destination_account_id.id if card_payment.destination_account_id else "None")

                # Generate journal entry explicitly to ensure account.move.line are created
                if card_payment.outstanding_account_id:
                    card_payment._generate_journal_entry()
                    _logger.info("[ADVANCE PAYMENT] Journal entry generated for card payment")
                else:
                    _logger.warning(
                        "[ADVANCE PAYMENT] Cannot generate journal entry: outstanding_account_id is missing!")

                # Post the payment (this will also post the journal entry if it's draft)
                card_payment.action_post()
                _logger.info("[ADVANCE PAYMENT] Card payment posted - ID: %d, State: %s, Move ID: %s",
                             card_payment.id, card_payment.state,
                             card_payment.move_id.id if card_payment.move_id else "None")
                if card_payment.move_id:
                    _logger.info("[ADVANCE PAYMENT] Card payment move - ID: %d, State: %s",
                                 card_payment.move_id.id, card_payment.move_id.state)
                    for line in card_payment.move_id.line_ids:
                        _logger.info("[ADVANCE PAYMENT]   - Line: Account=%s (ID: %d), Debit=%.2f, Credit=%.2f",
                                     line.account_id.name, line.account_id.id, line.debit, line.credit)
                else:
                    _logger.warning("[ADVANCE PAYMENT] Card payment has no move_id after action_post()!")

                # Create pos.payment
                card_pos_payment = self.env['pos.payment'].sudo().create({
                    'pos_order_id': pos_order.id,
                    'payment_method_id': card_pos_payment_method.id,
                    'amount': card_amount,
                    'payment_date': fields.Datetime.now(),
                })

            # For mixed payment, set main_payment to cash_payment if exists, else card_payment
            main_payment = cash_payment or card_payment
            main_pos_payment = cash_pos_payment or card_pos_payment

        else:
            print(12121212)
            # Single payment type (cash or card)
            # Get pos.payment.method for journal
            pos_payment_method = advance._get_pos_payment_method_from_journal(journal, pos_config)
            
            # Verify that payment method is linked to this POS config only
            # If it's linked to another config, don't set pos_payment_method_id to avoid constraint error
            can_use_payment_method = True
            if pos_payment_method:
                other_configs = self.env['pos.config'].search([
                    ('payment_method_ids', 'in', [pos_payment_method.id]),
                    ('id', '!=', pos_config.id),
                ])
                if other_configs:
                    _logger.warning("[ADVANCE PAYMENT] Payment method %s (ID: %d) is linked to other POS configs: %s. Not setting pos_payment_method_id to avoid constraint error.",
                                   pos_payment_method.name, pos_payment_method.id, other_configs.mapped('name'))
                    can_use_payment_method = False

            # Create account.payment
            payment_method_line = journal.inbound_payment_method_line_ids[:1]
            print(22222, payment_method_line)
            if not payment_method_line:
                raise ValidationError(
                    _('Please define an inbound payment method on journal %s.')
                    % journal.display_name
                )

            _logger.info("[ADVANCE PAYMENT] =========================================")
            _logger.info("[ADVANCE PAYMENT] Creating payment for advance %s", advance.name)
            _logger.info("[ADVANCE PAYMENT] Amount: %.2f, Destination Account: %s (ID: %d)",
                         amount_paid, pos_config.pos_advance_account_id.name, pos_config.pos_advance_account_id.id)
            _logger.info("[ADVANCE PAYMENT] Payment Method Line: %s, Payment Account: %s",
                         payment_method_line.name,
                         payment_method_line.payment_account_id.name if payment_method_line.payment_account_id else "None")
            
            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': partner_id,
                'amount': amount_paid,
                'currency_id': company.currency_id.id,
                'journal_id': journal.id,
                'payment_method_line_id': payment_method_line.id,
                'date': fields.Date.context_today(self),
                'memo': advance.name,
                'destination_account_id': pos_config.pos_advance_account_id.id,
                'pos_session_id': pos_session.id,
            }
            # Only set pos_payment_method_id if it's safe (not linked to other configs)
            if can_use_payment_method and pos_payment_method:
                payment_vals['pos_payment_method_id'] = pos_payment_method.id
            
            main_payment = self.env['account.payment'].sudo().create(payment_vals)
            # Flush to ensure computed fields are updated
            main_payment.flush_recordset(['outstanding_account_id', 'destination_account_id'])

            # Set outstanding_account_id to Cash/Bank or Card Account (journal.default_account_id) directly
            # This ensures advance payment is posted to Cash/Bank or Card Account, not Outstanding Receipts
            if journal and journal.default_account_id:
                main_payment.outstanding_account_id = journal.default_account_id.id
                main_payment.flush_recordset(['outstanding_account_id'])
                _logger.info("[ADVANCE PAYMENT] Set outstanding_account_id to Journal Account: %s (ID: %d)",
                             journal.default_account_id.name, journal.default_account_id.id)
            elif not main_payment.outstanding_account_id:
                # Fallback: get outstanding account from journal/company (should not happen)
                outstanding_account = main_payment._get_outstanding_account(main_payment.payment_type)
                main_payment.outstanding_account_id = outstanding_account.id
                main_payment.flush_recordset(['outstanding_account_id'])
                _logger.warning("[ADVANCE PAYMENT] Using fallback outstanding account: %s (ID: %d)",
                                outstanding_account.name, outstanding_account.id)

            _logger.info(
                "[ADVANCE PAYMENT] Payment created - ID: %d, State: %s, Outstanding Account: %s (ID: %s), Destination Account: %s (ID: %s)",
                main_payment.id, main_payment.state,
                main_payment.outstanding_account_id.name if main_payment.outstanding_account_id else "None",
                main_payment.outstanding_account_id.id if main_payment.outstanding_account_id else "None",
                main_payment.destination_account_id.name if main_payment.destination_account_id else "None",
                main_payment.destination_account_id.id if main_payment.destination_account_id else "None")

            # Generate journal entry explicitly to ensure account.move.line are created
            if main_payment.outstanding_account_id:
                main_payment._generate_journal_entry()
                _logger.info("[ADVANCE PAYMENT] Journal entry generated for payment")
            else:
                _logger.warning("[ADVANCE PAYMENT] Cannot generate journal entry: outstanding_account_id is missing!")

            # Post the payment (this will also post the journal entry if it's draft)
            main_payment.action_post()
            _logger.info("[ADVANCE PAYMENT] Payment posted - ID: %d, State: %s, Move ID: %s",
                         main_payment.id, main_payment.state,
                         main_payment.move_id.id if main_payment.move_id else "None")
            if main_payment.move_id:
                _logger.info("[ADVANCE PAYMENT] Payment move - ID: %d, State: %s",
                             main_payment.move_id.id, main_payment.move_id.state)
                for line in main_payment.move_id.line_ids:
                    _logger.info("[ADVANCE PAYMENT]   - Line: Account=%s (ID: %d), Debit=%.2f, Credit=%.2f",
                                 line.account_id.name, line.account_id.id, line.debit, line.credit)
            else:
                _logger.warning("[ADVANCE PAYMENT] Payment has no move_id after action_post()!")

            # Create pos.payment
            main_pos_payment = self.env['pos.payment'].sudo().create({
                'pos_order_id': pos_order.id,
                'payment_method_id': pos_payment_method.id,
                'amount': amount_paid,
                'payment_date': fields.Datetime.now(),
            })

        # Update pos.order amount_paid and state
        pos_order.amount_paid = amount_paid
        # Set state to 'paid' so payments appear in closing register
        pos_order.state = 'paid'

        # --------------------------------------------------
        # 5) MARK ADVANCE AS PAID
        # --------------------------------------------------
        payment_vals = {
            'payment_id': main_payment.id if main_payment else False,
            'state': 'paid',
            'pos_order_id': pos_order.id,
        }
        if cash_payment:
            payment_vals['cash_payment_id'] = cash_payment.id
        if card_payment:
            payment_vals['card_payment_id'] = card_payment.id

        advance.write(payment_vals)

        # --------------------------------------------------
        # 6) SEND NOTIFICATIONS AND EMAILS
        # --------------------------------------------------
        try:
            advance._send_advance_notifications()
        except Exception as e:
            # Don't fail the advance creation if notification fails
            pass

        return {
            'id': advance.id,
            'name': advance.name,
        }

    def _create_advance_transfer_move(self, invoice):
        self.ensure_one()

        partner = self.partner_id
        pos_config = self.pos_config_id
        company = self.company_id

        receivable_account = partner.property_account_receivable_id
        advance_account = pos_config.pos_advance_account_id

        unique_ref = _('Advance Transfer: %s (ID: %d)') % (self.name, self.id)

        move = self.env['account.move'].sudo().create({
            'move_type': 'entry',
            'date': invoice.invoice_date or fields.Date.context_today(self),
            'ref': unique_ref,
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

        _logger.info("[ADVANCE TRANSFER] Transfer move created - ID: %d, State: %s", move.id, move.state)
        move.action_post()
        _logger.info("[ADVANCE TRANSFER] Transfer move posted - ID: %d, State: %s", move.id, move.state)

        # Verify the move lines
        for line in move.line_ids:
            _logger.info("  - Line: Account=%s, Debit=%.2f, Credit=%.2f",
                         line.account_id.name, line.debit, line.credit)

        self.transfer_move_id = move.id
        return move

    # --------------------------------------------------
    # CREATE INVOICE + APPLY ADVANCE + RECONCILE
    # --------------------------------------------------
    def action_create_invoice(self, vals=None):
        payment_type = (vals or {}).get('payment_type')
        cash_amount = (vals or {}).get('cash_amount', 0.0) or 0.0
        card_amount = (vals or {}).get('card_amount', 0.0) or 0.0

        for advance in self:
            # Update payment type and amounts
            if payment_type:
                advance.payment_type = payment_type
                if payment_type == 'mixed':
                    advance.cash_amount = cash_amount
                    advance.card_amount = card_amount
                elif payment_type == 'cash':
                    advance.cash_amount = advance.remaining_amount
                    advance.card_amount = 0.0
                elif payment_type == 'card':
                    advance.cash_amount = 0.0
                    advance.card_amount = advance.remaining_amount

            if advance.invoice_id:
                raise ValidationError(_("Invoice already created."))

            if not advance.line_ids:
                raise ValidationError(_("No products to invoice."))

            company = advance.company_id
            partner = advance.partner_id
            pos_config = advance.pos_config_id

            # For mixed payment, check cash_payment_id or card_payment_id instead
            if advance.payment_type == 'mixed':
                if not advance.cash_payment_id and not advance.card_payment_id:
                    raise ValidationError(_("Advance payment not found (mixed payment requires at least one payment)."))
            else:
                if not advance.payment_id:
                    raise ValidationError(_("Advance payment not found."))

            # --------------------------------------------------
            # 1) GET POS SESSION
            # --------------------------------------------------
            pos_session = self.env['pos.session'].search([
                ('state', '=', 'opened'),
                ('config_id', '=', pos_config.id),
                ('company_id', '=', company.id),
            ], limit=1)

            if not pos_session:
                raise ValidationError(_("No open POS session found. Please open a POS session first."))

            # --------------------------------------------------
            # 2) CREATE POS ORDER WITH PRODUCTS (exclude employee_service and delivery_product)
            # --------------------------------------------------
            # ✅ IMPORTANT: Let Odoo calculate taxes automatically
            # ❌ DO NOT calculate taxes manually
            # ❌ DO NOT pass price_subtotal or price_subtotal_incl
            # ❌ DO NOT pass amount_tax or amount_total
            # ✅ Only pass: product_id, qty, price_unit, tax_ids
            # Odoo's _generate_pos_order_invoice() will handle everything
            
            pos_order_lines = []

            for line in advance.line_ids:
                product = line.product_id
                # Skip products with is_employee_service or is_delivery_product
                if product.is_employee_service or product.is_delivery_product:
                    continue

                # ✅ Create pos.order.line - Let POS calculate taxes automatically
                # Note: price_subtotal and price_subtotal_incl are required fields
                # We pass simple values (price_unit * qty) without tax calculation
                # POS will recalculate them correctly when creating invoice using fiscal_position_id
                simple_subtotal = line.price_unit * line.qty
                pos_order_lines.append((0, 0, {
                    'product_id': product.id,
                    'qty': line.qty,
                    'price_unit': line.price_unit,
                    'price_subtotal': simple_subtotal,  # Required field - simple calculation
                    'price_subtotal_incl': simple_subtotal,  # Required field - simple calculation
                }))

            if not pos_order_lines:
                raise ValidationError(_("No products to invoice (all products are employee/delivery services)."))

            # Get employee_id from vals if provided
            employee_id = (vals or {}).get('employee_id', False)

            # Create the POS order
            # ✅ Let POS calculate everything automatically - DO NOT calculate taxes manually
            # ✅ IMPORTANT: Add fiscal_position_id - taxes in POS always go through Fiscal Position
            pos_order_vals = {
                'session_id': pos_session.id,
                'partner_id': partner.id,
                'config_id': pos_config.id,
                'company_id': company.id,
                'pricelist_id': partner.property_product_pricelist.id or pos_config.pricelist_id.id,
                'fiscal_position_id': partner.property_account_position_id.id or False,
                'lines': pos_order_lines,
                'amount_total': 0.0,  # Required field - POS will calculate automatically
                'amount_tax': 0.0,  # Required field - POS will calculate automatically
                'amount_paid': 0.0,  # Will be updated after adding payments
                'amount_return': 0.0,
                'advance_payment_id': advance.id,
            }
            if employee_id:
                pos_order_vals['employee_id'] = employee_id

            pos_order = self.env['pos.order'].sudo().create(pos_order_vals)
            
            # ✅ IMPORTANT: Set tax_ids for each line from product.taxes_id (required for _compute_amount_line_all)
            # Then recalculate price_subtotal and price_subtotal_incl using POS's internal method
            # This ensures taxes are calculated correctly with fiscal_position_id before invoice creation
            for line in pos_order.lines:
                # Set tax_ids from product (POS does this automatically in onchange, but we need to do it manually)
                if line.product_id:
                    line.sudo().tax_ids = line.product_id.taxes_id.filtered_domain(
                        self.env['account.tax']._check_company_domain(company)
                    )
                    # Use POS's internal method to calculate correct values with fiscal position
                    computed_values = line._compute_amount_line_all()
                    line.sudo().write(computed_values)
            
            # ✅ DO NOT call _compute_prices() - it may interfere with invoice generation
            # _generate_pos_order_invoice() will recalculate everything using its internal logic

            # --------------------------------------------------
            # 3) CREATE POS.PAYMENT(S) FOR REMAINING AMOUNT (if any) - BEFORE INVOICE
            # --------------------------------------------------
            # IMPORTANT: Create pos.payment BEFORE creating invoice
            # Because invoice creation may change pos_order.state to 'done', which prevents pos.payment creation
            _logger.info("[ADVANCE COMPLETION] =========================================")
            _logger.info("[ADVANCE COMPLETION] Creating payments for remaining amount - Advance: %s (ID: %d)", advance.name, advance.id)
            _logger.info("[ADVANCE COMPLETION] Remaining Amount: %.2f, Payment Type: %s", advance.remaining_amount, advance.payment_type)
            
            # Count existing pos.payment records before creation
            existing_pos_payments_before = self.env['pos.payment'].search_count([
                ('pos_order_id', '=', pos_order.id),
            ])
            _logger.info("[ADVANCE COMPLETION] Existing pos.payment records before: %d", existing_pos_payments_before)
            
            if advance.remaining_amount > 0:
                if advance.payment_type == 'mixed':
                    cash_journal = pos_config.pos_cash_journal_id if cash_amount > 0 else None
                    card_journal = pos_config.pos_card_journal_id if card_amount > 0 else None

                    if cash_amount > 0 and cash_journal:
                        cash_pos_payment_method = advance._get_pos_payment_method_from_journal(cash_journal, pos_config)
                        _logger.info("[ADVANCE COMPLETION] Creating cash pos.payment - Amount: %.2f, Method: %s", 
                                    cash_amount, cash_pos_payment_method.name)
                        cash_pos_payment = self.env['pos.payment'].sudo().create({
                            'pos_order_id': pos_order.id,
                            'payment_method_id': cash_pos_payment_method.id,
                            'amount': cash_amount,
                            'payment_date': fields.Datetime.now(),
                        })
                        _logger.info("[ADVANCE COMPLETION] ✓ Created cash pos.payment - ID: %d, Amount: %.2f", 
                                    cash_pos_payment.id, cash_pos_payment.amount)

                    if card_amount > 0 and card_journal:
                        card_pos_payment_method = advance._get_pos_payment_method_from_journal(card_journal, pos_config)
                        _logger.info("[ADVANCE COMPLETION] Creating card pos.payment - Amount: %.2f, Method: %s", 
                                    card_amount, card_pos_payment_method.name)
                        card_pos_payment = self.env['pos.payment'].sudo().create({
                            'pos_order_id': pos_order.id,
                            'payment_method_id': card_pos_payment_method.id,
                            'amount': card_amount,
                            'payment_date': fields.Datetime.now(),
                        })
                        _logger.info("[ADVANCE COMPLETION] ✓ Created card pos.payment - ID: %d, Amount: %.2f", 
                                    card_pos_payment.id, card_pos_payment.amount)
                else:
                    journal = advance._get_payment_journal()
                    pos_payment_method = advance._get_pos_payment_method_from_journal(journal, pos_config)
                    _logger.info("[ADVANCE COMPLETION] Creating pos.payment - Amount: %.2f, Method: %s, Journal: %s", 
                                advance.remaining_amount, pos_payment_method.name, journal.name)
                    pos_payment = self.env['pos.payment'].sudo().create({
                        'pos_order_id': pos_order.id,
                        'payment_method_id': pos_payment_method.id,
                        'amount': advance.remaining_amount,
                        'payment_date': fields.Datetime.now(),
                    })
                    _logger.info("[ADVANCE COMPLETION] ✓ Created pos.payment - ID: %d, Amount: %.2f", 
                                pos_payment.id, pos_payment.amount)
            else:
                _logger.info("[ADVANCE COMPLETION] No remaining amount - skipping pos.payment creation")
            
            # Count existing pos.payment records after creation
            existing_pos_payments_after = self.env['pos.payment'].search_count([
                ('pos_order_id', '=', pos_order.id),
            ])
            _logger.info("[ADVANCE COMPLETION] Total pos.payment records after: %d (Created: %d)", 
                        existing_pos_payments_after, existing_pos_payments_after - existing_pos_payments_before)
            
            # Count account.payment records before invoice creation
            account_payments_before = self.env['account.payment'].search_count([
                ('partner_id', '=', partner.id),
                ('pos_session_id', '=', pos_session.id),
                ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=5)),
            ])
            _logger.info("[ADVANCE COMPLETION] account.payment records before invoice creation: %d", account_payments_before)

            # --------------------------------------------------
            # 4) GENERATE INVOICE FROM POS ORDER FIRST
            # --------------------------------------------------
            # Create invoice first to get accurate sales and tax amounts
            pos_order.write({'to_invoice': True})
            invoice = pos_order._generate_pos_order_invoice()
            _logger.info("[ADVANCE COMPLETION] Invoice created - ID: %d, Amount: %.2f",
                         invoice.id, invoice.amount_total)
            
            # Count account.payment records after invoice creation
            account_payments_after = self.env['account.payment'].search_count([
                ('partner_id', '=', partner.id),
                ('pos_session_id', '=', pos_session.id),
                ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=5)),
            ])
            _logger.info("[ADVANCE COMPLETION] account.payment records after invoice creation: %d (New: %d)", 
                        account_payments_after, account_payments_after - account_payments_before)
            
            if account_payments_after > account_payments_before:
                new_payments = self.env['account.payment'].search([
                    ('partner_id', '=', partner.id),
                    ('pos_session_id', '=', pos_session.id),
                    ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=5)),
                ], order='create_date desc', limit=account_payments_after - account_payments_before)
                _logger.info("[ADVANCE COMPLETION] ⚠️ New account.payment records created during completion:")
                for payment in new_payments:
                    _logger.info("  - Payment ID: %d, Name: %s, Amount: %.2f, State: %s", 
                               payment.id, payment.name, payment.amount, payment.state)
            else:
                _logger.info("[ADVANCE COMPLETION] ✓ No new account.payment records created (expected - only pos.payment created)")

            # --------------------------------------------------
            # 4) CREATE COMPLETION JOURNAL ENTRY
            # --------------------------------------------------
            # IMPORTANT: The invoice already contains Sales and Tax lines.
            # We should NOT duplicate them in the completion move.
            # The completion move should only record:
            # - Debit: Cash/Bank (remaining amount)
            # - Debit: Advance Account (advance amount)
            # - Credit: Receivable Account (to reconcile with invoice)
            #
            # The invoice already has:
            # - Debit: Receivable
            # - Credit: Sales
            # - Credit: Tax
            #
            # So the completion move will reconcile with the invoice's Receivable line.

            _logger.info("[ADVANCE COMPLETION] Invoice created - ID: %d, Amount: %.2f",
                         invoice.id, invoice.amount_total)
            _logger.info(
                "[ADVANCE COMPLETION] Invoice already contains Sales and Tax lines - we will NOT duplicate them in completion move")

            advance_account = pos_config.pos_advance_account_id
            receivable_account = partner.property_account_receivable_id
            move_line_vals = []

            # --------------------------------------------------
            # Debit: Cash/Bank (remaining amount)
            # --------------------------------------------------
            if advance.remaining_amount > 0:
                if advance.payment_type == 'mixed':
                    # For mixed payment, we need to create separate debit lines for cash and card
                    if cash_amount > 0:
                        cash_journal = pos_config.pos_cash_journal_id
                        if cash_journal and cash_journal.default_account_id:
                            move_line_vals.append((0, 0, {
                                'name': _('Complete Advance Payment - Cash: %s') % advance.name,
                                'partner_id': partner.id,
                                'account_id': cash_journal.default_account_id.id,
                                'debit': cash_amount,
                                'credit': 0.0,
                            }))

                    if card_amount > 0:
                        card_journal = pos_config.pos_card_journal_id
                        if card_journal and card_journal.default_account_id:
                            move_line_vals.append((0, 0, {
                                'name': _('Complete Advance Payment - Card: %s') % advance.name,
                                'partner_id': partner.id,
                                'account_id': card_journal.default_account_id.id,
                                'debit': card_amount,
                                'credit': 0.0,
                            }))
                else:
                    # Single payment type
                    journal = advance._get_payment_journal()
                    if journal and journal.default_account_id:
                        move_line_vals.append((0, 0, {
                            'name': _('Complete Advance Payment: %s') % advance.name,
                            'partner_id': partner.id,
                            'account_id': journal.default_account_id.id,
                            'debit': advance.remaining_amount,
                            'credit': 0.0,
                        }))

            # --------------------------------------------------
            # Debit: Advance Account (to zero it out)
            # --------------------------------------------------
            move_line_vals.append((0, 0, {
                'name': _('Apply Advance Payment: %s') % advance.name,
                'partner_id': partner.id,
                'account_id': advance_account.id,
                'debit': advance.amount_paid,
                'credit': 0.0,
            }))

            # --------------------------------------------------
            # Credit: Receivable Account (to reconcile with invoice)
            # --------------------------------------------------
            # Calculate total debit (Cash/Bank + Advance Account)
            total_debit = sum(line_vals[2].get('debit', 0.0) for line_vals in move_line_vals if
                              isinstance(line_vals, tuple) and len(line_vals) > 2)

            # The Receivable credit should equal total_debit (which should equal invoice.amount_total)
            # Total Debit = Cash/Bank (remaining) + Advance Account (advance) = invoice.amount_total
            # Total Credit = Receivable = invoice.amount_total
            receivable_credit = invoice.amount_total

            move_line_vals.append((0, 0, {
                'name': _('Invoice Receivable: %s') % invoice.name,
                'partner_id': partner.id,
                'account_id': receivable_account.id,
                'debit': 0.0,
                'credit': receivable_credit,
            }))

            # Verify balance: total_debit should equal invoice.amount_total
            balance_diff = total_debit - invoice.amount_total
            currency_rounding = company.currency_id.rounding or 0.01

            _logger.info("[ADVANCE COMPLETION] Creating completion move for advance %s", advance.name)
            _logger.info("[ADVANCE COMPLETION] Remaining Amount: %.2f, Advance Amount: %.2f",
                         advance.remaining_amount, advance.amount_paid)
            _logger.info(
                "[ADVANCE COMPLETION] Total Debit: %.2f, Receivable Credit: %.2f, Invoice Total: %.2f, Balance Diff: %.2f",
                total_debit, receivable_credit, invoice.amount_total, balance_diff)

            # If not balanced, adjust Cash/Bank line
            # Use float_compare for accurate comparison with currency rounding
            balance_compare = float_compare(abs(balance_diff), currency_rounding, precision_rounding=currency_rounding)

            if balance_compare >= 0:  # balance_diff >= currency_rounding (including equal)
                _logger.warning(
                    "[ADVANCE COMPLETION] Warning: Entry not balanced (Diff: %.2f >= Rounding: %.2f). Adjusting Cash/Bank line.",
                    balance_diff, currency_rounding)
                # Find the Cash/Bank debit line (first debit line that's not Advance Account)
                cash_bank_line_found = False
                for i in range(len(move_line_vals) - 1):  # Skip the Receivable line
                    line_val = move_line_vals[i]
                    if isinstance(line_val, tuple) and len(line_val) > 2:
                        line_dict = line_val[2]
                        if (line_dict.get('debit', 0.0) > 0.0 and
                                line_dict.get('account_id') != advance_account.id):
                            # This is the Cash/Bank line - adjust it
                            current_debit = line_dict.get('debit', 0.0)
                            line_dict['debit'] = current_debit - balance_diff  # Subtract difference to balance
                            _logger.info(
                                "[ADVANCE COMPLETION] Adjusted Cash/Bank line debit from %.2f to %.2f to balance entry (diff: %.2f)",
                                current_debit, current_debit - balance_diff, balance_diff)
                            cash_bank_line_found = True
                            break

                if not cash_bank_line_found:
                    _logger.warning(
                        "[ADVANCE COMPLETION] Could not find Cash/Bank line to adjust - entry may not be balanced")
            else:
                _logger.info("[ADVANCE COMPLETION] Entry is balanced (diff: %.2f < rounding: %.2f)", balance_diff,
                             currency_rounding)

            # Create the journal entry
            # Use POS journal or fallback to first available journal
            journal = pos_config.journal_id
            if not journal:
                journal = self.env['account.journal'].search([
                    ('company_id', '=', company.id),
                    ('type', 'in', ['general', 'sale']),
                ], limit=1)
            if not journal:
                raise ValidationError(_("No journal found to create completion move. Please configure POS journal."))

            # Generate unique reference to avoid "Reference must be unique per company" error
            # Use advance.id to ensure uniqueness even if advance.name is duplicated
            unique_ref = _('Complete Advance Payment: %s (ID: %d)') % (advance.name, advance.id)

            completion_move = self.env['account.move'].sudo().create({
                'move_type': 'entry',
                'date': fields.Date.context_today(self),
                'ref': unique_ref,
                'company_id': company.id,
                'journal_id': journal.id,
                'line_ids': move_line_vals,
            })

            completion_move.action_post()

            _logger.info("[ADVANCE COMPLETION] Completion move posted - ID: %d", completion_move.id)
            for line in completion_move.line_ids:
                _logger.info("[ADVANCE COMPLETION]   - Line: Account=%s, Debit=%.2f, Credit=%.2f",
                             line.account_id.name, line.debit, line.credit)

            # --------------------------------------------------
            # 6) RECONCILE INVOICE WITH COMPLETION MOVE
            # --------------------------------------------------

            # Reconcile invoice receivable with completion move receivable
            invoice_receivable_lines = invoice.line_ids.filtered(
                lambda l: l.account_id and l.account_id.account_type == 'asset_receivable' and not l.reconciled
            )
            completion_receivable_lines = completion_move.line_ids.filtered(
                lambda l: l.account_id.id == receivable_account.id and not l.reconciled
            )

            if invoice_receivable_lines and completion_receivable_lines:
                (invoice_receivable_lines | completion_receivable_lines).reconcile()
                _logger.info("[ADVANCE COMPLETION] Invoice reconciled with completion move - Invoice is now Paid")
            else:
                _logger.warning(
                    "[ADVANCE COMPLETION] Could not reconcile invoice - Invoice Receivable Lines: %d, Completion Receivable Lines: %d",
                    len(invoice_receivable_lines), len(completion_receivable_lines))

            # --------------------------------------------------
            # 7) UPDATE POS ORDER AMOUNT_PAID AND STATE
            # --------------------------------------------------
            # Note: pos.payment records were already created before invoice creation (step 3)
            # to avoid constraint error when order state becomes 'done'
            pos_order.amount_paid = advance.remaining_amount if advance.remaining_amount > 0 else 0.0
            # Ensure state is 'paid' so payments appear in closing register
            if pos_order.state != 'paid':
                pos_order.state = 'paid'

            # --------------------------------------------------
            # 8) MARK COMPLETED AND LINK POS ORDER AND INVOICE
            # --------------------------------------------------
            advance.write({
                'completion_move_id': completion_move.id,
                'invoice_id': invoice.id,
                'state': 'invoiced',
                'pos_order_id': pos_order.id,
            })
            
            # --------------------------------------------------
            # 9) LOG SUMMARY OF ALL PAYMENTS CREATED
            # --------------------------------------------------
            _logger.info("[ADVANCE COMPLETION] =========================================")
            _logger.info("[ADVANCE COMPLETION] PAYMENT SUMMARY for Advance: %s (ID: %d)", advance.name, advance.id)
            
            # Summary of pos.payment records
            all_pos_payments = self.env['pos.payment'].search([
                ('pos_order_id', '=', pos_order.id),
            ])
            _logger.info("[ADVANCE COMPLETION] pos.payment records created: %d", len(all_pos_payments))
            total_pos_payment_amount = 0.0
            for pos_payment in all_pos_payments:
                _logger.info("  - pos.payment ID: %d, Amount: %.2f, Method: %s, Date: %s", 
                           pos_payment.id, pos_payment.amount, pos_payment.payment_method_id.name, pos_payment.payment_date)
                total_pos_payment_amount += pos_payment.amount
            _logger.info("[ADVANCE COMPLETION] Total pos.payment amount: %.2f", total_pos_payment_amount)
            
            # Summary of account.payment records (should be 0 - only pos.payment created)
            final_account_payments = self.env['account.payment'].search([
                ('partner_id', '=', partner.id),
                ('pos_session_id', '=', pos_session.id),
                ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=5)),
            ])
            _logger.info("[ADVANCE COMPLETION] account.payment records in session: %d", len(final_account_payments))
            if final_account_payments:
                _logger.warning("[ADVANCE COMPLETION] ⚠️ account.payment records found (should be 0 for completion):")
                for payment in final_account_payments:
                    _logger.warning("  - account.payment ID: %d, Name: %s, Amount: %.2f, State: %s, Memo: %s", 
                                  payment.id, payment.name, payment.amount, payment.state, payment.memo or "None")
            else:
                _logger.info("[ADVANCE COMPLETION] ✓ No account.payment records created (expected - only pos.payment)")
            
            # Summary of advance payments (original)
            _logger.info("[ADVANCE COMPLETION] Original advance payment:")
            if advance.payment_id:
                _logger.info("  - account.payment ID: %d, Amount: %.2f", advance.payment_id.id, advance.payment_id.amount)
            if advance.cash_payment_id:
                _logger.info("  - Cash account.payment ID: %d, Amount: %.2f", advance.cash_payment_id.id, advance.cash_payment_id.amount)
            if advance.card_payment_id:
                _logger.info("  - Card account.payment ID: %d, Amount: %.2f", advance.card_payment_id.id, advance.card_payment_id.amount)
            
            _logger.info("[ADVANCE COMPLETION] =========================================")

            # --------------------------------------------------
            # 8) CREATE POS.PLEDGE RECORD IF NEEDED
            # --------------------------------------------------
            # Check if any line has pledge/employee/delivery products
            has_pledge = any(line.product_id.is_pledge_product for line in advance.line_ids)
            has_employee = any(line.product_id.is_employee_service for line in advance.line_ids)
            has_delivery = any(line.product_id.is_delivery_product for line in advance.line_ids)

            if has_pledge or has_employee or has_delivery:
                # Calculate amounts
                pledge_amount = sum(
                    (line.product_id.pledge_amount or (line.price_unit * line.qty))
                    for line in advance.line_ids
                    if line.product_id.is_pledge_product
                )
                employee_amount = sum(
                    line.subtotal for line in advance.line_ids
                    if line.product_id.is_employee_service
                )
                delivery_amount = sum(
                    line.subtotal for line in advance.line_ids
                    if line.product_id.is_delivery_product
                )

                # Determine case type
                if has_employee and not has_pledge and not has_delivery:
                    case_type = 'case1'  # Employee Only
                elif has_pledge and not has_delivery and not has_employee:
                    case_type = 'case2'  # Pledge Only
                elif has_pledge and has_delivery and not has_employee:
                    case_type = 'case3'  # Pledge + Delivery
                elif has_pledge and has_employee and has_delivery:
                    case_type = 'case4'  # All Three: Pledge + Employee + Delivery
                elif has_pledge and has_employee and not has_delivery:
                    case_type = 'case5'  # Pledge + Employee (no delivery)
                elif has_employee and has_delivery and not has_pledge:
                    case_type = 'case6'  # Employee + Delivery (no pledge)
                else:
                    case_type = 'mixed'

                # Get pledge products
                pledge_products = [
                    line.product_id.id for line in advance.line_ids
                    if line.product_id.is_pledge_product
                ]

                # Get employee product
                employee_line = next(
                    (line for line in advance.line_ids if line.product_id.is_employee_service),
                    None
                )
                employee_product_id = employee_line.product_id.id if employee_line else False

                # Get delivery product
                delivery_line = next(
                    (line for line in advance.line_ids if line.product_id.is_delivery_product),
                    None
                )
                delivery_product_id = delivery_line.product_id.id if delivery_line else False

                # Create pledge record
                # Note: employee_id will be taken from pos_order.employee_id in create_from_pos
                pledge_vals = {
                    'pos_order_id': pos_order.id,
                    'pos_config_id': pos_config.id,
                    'partner_id': partner.id,
                    'case_type': case_type,
                    'pledge_amount': pledge_amount or 0,
                    'employee_amount': employee_amount or 0,
                    'delivery_amount': delivery_amount or 0,
                    'pledge_products': [(6, 0, pledge_products)],
                    'employee_product_id': employee_product_id,
                    'delivery_product_id': delivery_product_id,
                }

                try:
                    pledge_id = self.env['pos.pledge'].create_from_pos(pledge_vals)
                    _logger.info("[ADVANCE] Created pos.pledge record ID %s for advance %s", pledge_id, advance.name)
                except Exception as e:
                    _logger.error("[ADVANCE] Failed to create pos.pledge record: %s", str(e))
                    # Don't fail invoice creation if pledge creation fails
                    pass

            # --------------------------------------------------
            # 9) CREATE STOCK PICKING AND MOVES (using Odoo's standard method)
            # --------------------------------------------------
            # Check if picking already exists for this order
            existing_pickings = pos_order.picking_ids.filtered(lambda p: p.state != 'cancel')
            if existing_pickings:
                _logger.info("[ADVANCE] Picking already exists for order %s (ID: %d), skipping creation",
                             pos_order.name, pos_order.id)
            else:
                # Double-check if picking should be created
                # _create_order_picking() only creates picking if _should_create_picking_real_time() returns True
                if not pos_order._should_create_picking_real_time():
                    _logger.info(
                        "[ADVANCE] Picking creation not required for order %s (ID: %d) - stock update at closing",
                        pos_order.name, pos_order.id)
                else:
                    # Use savepoint to protect main transaction from picking creation errors
                    # The error can occur in both INSERT (create) and UPDATE (write/action_done) operations
                    try:
                        with self.env.cr.savepoint():
                            # Use Odoo's built-in method to create picking from POS order
                            pos_order._create_order_picking()
                            _logger.info("[ADVANCE] Successfully created picking for order %s (ID: %d)", pos_order.name,
                                         pos_order.id)
                    except Exception as e:
                        error_msg = str(e)
                        # Check if it's a duplicate key constraint violation (can occur in INSERT or UPDATE)
                        # The error can be raised as ValidationError with message "Reference must be unique per company!"
                        # or as IntegrityError with message "duplicate key value violates unique constraint..."
                        is_duplicate_error = (
                                'duplicate key value violates unique constraint "stock_picking_name_uniq"' in error_msg.lower() or
                                'stock_picking_name_uniq' in error_msg.lower() or
                                'reference must be unique per company' in error_msg.lower() or
                                (
                                            'duplicate' in error_msg.lower() and 'key' in error_msg.lower() and 'stock_picking' in error_msg.lower())
                        )

                        if is_duplicate_error:
                            _logger.warning(
                                "[ADVANCE] Duplicate picking name detected for order %s (ID: %d). This may be due to a race condition or existing picking.",
                                pos_order.name, pos_order.id)

                            # Refresh to check if picking was created and linked despite the error
                            pos_order.invalidate_recordset(['picking_ids'])
                            if pos_order.picking_ids:
                                _logger.info(
                                    "[ADVANCE] Picking was created and linked successfully despite error (race condition handled)")
                            else:
                                # Try to find and link existing picking by origin (pos_order.name)
                                existing_picking = self.env['stock.picking'].sudo().search([
                                    ('origin', '=', pos_order.name),
                                    ('company_id', '=', company.id),
                                    ('state', '!=', 'cancel'),
                                ], limit=1)

                                if existing_picking and not existing_picking.pos_order_id:
                                    # Link the existing picking to this order (use savepoint to handle any write errors)
                                    try:
                                        with self.env.cr.savepoint():
                                            existing_picking.write({
                                                'pos_order_id': pos_order.id,
                                                'pos_session_id': pos_order.session_id.id if pos_order.session_id else False,
                                            })
                                            _logger.info(
                                                "[ADVANCE] Linked existing picking %s (ID: %d) to order %s (ID: %d)",
                                                existing_picking.name, existing_picking.id, pos_order.name,
                                                pos_order.id)
                                    except Exception as link_error:
                                        _logger.warning(
                                            "[ADVANCE] Could not link existing picking %s (ID: %d) to order %s (ID: %d): %s. This is non-critical.",
                                            existing_picking.name, existing_picking.id, pos_order.name, pos_order.id,
                                            str(link_error))
                                else:
                                    _logger.warning(
                                        "[ADVANCE] Could not find or link existing picking for order %s (ID: %d). This is non-critical - picking may be created later during session closing.",
                                        pos_order.name, pos_order.id)
                        else:
                            _logger.warning(
                                "[ADVANCE] Failed to create picking for order %s (ID: %d): %s. This is non-critical - picking may be created later during session closing.",
                                pos_order.name, pos_order.id, error_msg)

            return invoice

    def action_mark_invoiced(self, invoice):
        self.write({'invoice_id': invoice.id, 'state': 'invoiced'})

    def _send_advance_notifications(self):
        """
        Send notifications and emails to users configured in pickup_pos_id.advance_notification_user_ids
        """
        self.ensure_one()

        # Get pickup POS config
        pickup_pos = self.pickup_pos_id
        if not pickup_pos:
            return

        # Get notification users from pickup location
        notification_users = pickup_pos.advance_notification_user_ids
        if not notification_users:
            return

        # Prepare notification content
        partner = self.partner_id
        currency = self.currency_id

        # Build email body
        email_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #007bff;">New Advance Order Created</h2>

            <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Advance Number:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{self.name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Customer:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{partner.name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Customer Phone:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{partner.phone or 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Total Expected:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{currency.symbol} {self.total_expected:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Amount Paid:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{currency.symbol} {self.amount_paid:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Remaining Amount:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong style="color: #dc3545;">{currency.symbol} {self.remaining_amount:,.2f}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Payment Type:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{self.payment_type.upper()}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Pickup Location:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{pickup_pos.name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Due Date:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{self.due_date.strftime('%Y-%m-%d') if self.due_date else 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Created Date:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{self.create_date.strftime('%Y-%m-%d %H:%M:%S')}</td>
                </tr>
            </table>

            <h3 style="margin-top: 30px; color: #28a745;">Products:</h3>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Product</th>
                        <th style="padding: 10px; text-align: center; border: 1px solid #ddd;">Quantity</th>
                        <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Unit Price</th>
                        <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Subtotal</th>
                    </tr>
                </thead>
                <tbody>
        """

        # Add product lines
        for line in self.line_ids:
            email_body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;">{line.product_id.name}</td>
                        <td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{line.qty}</td>
                        <td style="padding: 8px; text-align: right; border: 1px solid #ddd;">{currency.symbol} {line.price_unit:,.2f}</td>
                        <td style="padding: 8px; text-align: right; border: 1px solid #ddd;">{currency.symbol} {line.subtotal:,.2f}</td>
                    </tr>
            """

        email_body += """
                </tbody>
            </table>

            <p style="margin-top: 30px; color: #6c757d;">
                <a href="{base_url}/web#id={advance_id}&model=pos.advance.payment&view_type=form" 
                   style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Advance Order
                </a>
            </p>
        </div>
        """

        # Get base URL
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', 'http://localhost:8069')

        # Replace placeholders
        email_body = email_body.format(
            base_url=base_url,
            advance_id=self.id
        )

        # Send notification and email to each user
        notification_body = f'New Advance Order: {self.name}\nCustomer: {partner.name}\nTotal: {currency.symbol} {self.total_expected:,.2f}\nPaid: {currency.symbol} {self.amount_paid:,.2f}\nRemaining: {currency.symbol} {self.remaining_amount:,.2f}'

        # Post message in chatter first (without partner_ids to avoid auto-notification)
        message = self.message_post(
            body=notification_body,
            subject=f'New Advance Order: {self.name}',
            email_layout_xmlid='mail.mail_notification_light',
            subtype_xmlid='mail.mt_comment',
            mail_auto_delete=False,
        )

        # Now manually notify the specific users using _notify_thread
        # This ensures proper inbox notifications are created
        partner_ids = [user.partner_id.id for user in notification_users]

        # Add partners as followers first
        self.message_subscribe(partner_ids=partner_ids)

        # Use _notify_get_recipients to get proper recipients_data format
        # We need to pass partner_ids in the message to get proper recipients
        msg_vals = {
            'partner_ids': partner_ids,
            'model': self._name,
            'res_id': self.id,
        }

        # Get recipients data using the standard method
        recipients_data = self._notify_get_recipients(message, msg_vals=msg_vals)

        # Filter to only include our notification users and force inbox notification
        notification_partner_ids = set(partner_ids)
        recipients_data = [
            r for r in recipients_data
            if r.get('id') in notification_partner_ids
        ]

        # Force inbox notification type
        for r in recipients_data:
            r['notif'] = 'inbox'

        # Call _notify_thread_by_inbox to create notifications and send bus messages
        if recipients_data:
            self._notify_thread_by_inbox(message, recipients_data)

        # Send email notifications separately
        for user in notification_users:
            try:
                if user.email:
                    mail_values = {
                        'subject': f'New Advance Order: {self.name}',
                        'body_html': email_body,
                        'email_to': user.email,
                        'email_from': self.env.user.email_formatted or self.env.company.email,
                        'author_id': self.env.user.partner_id.id,
                        'model': 'pos.advance.payment',
                        'res_id': self.id,
                    }

                    mail = self.env['mail.mail'].sudo().create(mail_values)
                    mail.send()

            except Exception:
                pass

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
