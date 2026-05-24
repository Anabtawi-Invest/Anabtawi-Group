# pos_delivery_amount/models/pos_session.py

import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    delivery_amount = fields.Monetary(
        string='Delivery Amount',
        currency_field='currency_id',
        default=0.0,
        readonly=True,
        help='Amount entered by cashier to be deposited to the bank on the next business day.',
    )

    delivery_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Delivery Journal Entry',
        readonly=True,
        copy=False,
        help='Journal entry created for the delivery amount at session closing.',
    )

    # ------------------------------------------------------------------
    # Public RPC Method (called from POS frontend)
    # ------------------------------------------------------------------

    @api.model
    def action_process_delivery_amount(self, session_id, delivery_amount):
        """
        Validate, create and post the delivery journal entry.
        Called by the POS frontend just before the session is fully closed.

        :param session_id: int  – ID of the pos.session record
        :param delivery_amount: float – amount entered by the cashier
        :returns: dict with keys 'success' (bool) and 'message' (str)
        """
        session = self.browse(session_id)
        if not session.exists():
            return {'success': False, 'message': _('POS session not found.')}

        try:
            delivery_amount = float(delivery_amount)
        except (TypeError, ValueError):
            return {
                'success': False,
                'message': _('Invalid delivery amount value.'),
            }

        # ---- 1. Validate amount ----------------------------------------
        validation_result = session._validate_delivery_amount(delivery_amount)
        if not validation_result['success']:
            return validation_result

        # ---- 2. If zero, skip entry creation ---------------------------
        if delivery_amount == 0.0:
            session.sudo().write({'delivery_amount': 0.0})
            session._log_delivery_chatter(delivery_amount, move=None)
            return {'success': True, 'message': _('Delivery Amount processed successfully.')}

        # ---- 3. Validate configuration ---------------------------------
        config_result = session._validate_delivery_config()
        if not config_result['success']:
            return config_result

        # ---- 4. Create & post journal entry ----------------------------
        try:
            move = session._create_delivery_journal_entry(delivery_amount)
        except (UserError, ValidationError) as exc:
            _logger.exception('Delivery amount journal entry creation failed: %s', exc)
            return {'success': False, 'message': str(exc)}
        except Exception as exc:
            _logger.exception('Unexpected error creating delivery journal entry: %s', exc)
            return {
                'success': False,
                'message': _('Journal entry creation failed. Session closing aborted.'),
            }

        # ---- 5. Persist data on session --------------------------------
        session.sudo().write({
            'delivery_amount': delivery_amount,
            'delivery_move_id': move.id,
        })

        # ---- 6. Chatter log --------------------------------------------
        session._log_delivery_chatter(delivery_amount, move=move)

        return {'success': True, 'message': _('Delivery Amount processed successfully.')}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_delivery_amount(self, delivery_amount):
        """Return success/failure dict after checking amount boundaries."""
        if delivery_amount < 0.0:
            return {
                'success': False,
                'message': _('Delivery Amount cannot be negative.'),
            }

        cash_balance = self._get_counted_cash_balance()

        if delivery_amount > cash_balance:
            return {
                'success': False,
                'message': _(
                    'Delivery Amount cannot exceed counted cash balance.'
                ),
            }

        return {'success': True}

    def _validate_delivery_config(self):
        """Ensure required configuration fields are set."""
        config = self.config_id
        if not config.delivery_intermediate_account_id:
            return {
                'success': False,
                'message': _(
                    'Intermediate Account is not configured on the POS settings. '
                    'Please configure it before closing the session.'
                ),
            }
        if not config.delivery_journal_id:
            return {
                'success': False,
                'message': _(
                    'Delivery Journal is not configured on the POS settings. '
                    'Please configure it before closing the session.'
                ),
            }
        return {'success': True}

    def _get_counted_cash_balance(self):
        """
        Return the counted closing cash balance for this session.
        Uses the last closing statement line for the cash payment method.
        Falls back to the theoretical closing balance if no manual count exists.
        """
        cash_pm = self._get_cash_payment_method()
        if not cash_pm:
            return 0.0

        # In Odoo 19 the closing balance is stored on pos.payment.method statement
        # via bank statement lines linked to this session.
        # We read the last 'closing_control' statement amount.
        statement_lines = self.env['account.bank.statement.line'].search([
            ('pos_session_id', '=', self.id),
            ('journal_id', '=', cash_pm.journal_id.id),
        ])
        if statement_lines:
            return sum(statement_lines.mapped('amount'))

        # Fallback: use theoretical cash at close
        return self.cash_register_balance_end_real or 0.0

    def _get_cash_payment_method(self):
        """Return the cash payment method linked to this session's config."""
        return self.config_id.payment_method_ids.filtered(
            lambda pm: pm.is_cash_count and pm.journal_id.type == 'cash'
        )[:1]

    def _get_cash_account(self):
        """Return the default cash account from the POS cash journal."""
        cash_pm = self._get_cash_payment_method()
        if not cash_pm:
            raise UserError(
                _('No cash payment method found for this POS configuration.')
            )
        journal = cash_pm.journal_id
        account = (
            journal.default_account_id
            or journal.payment_debit_account_id
        )
        if not account:
            raise UserError(
                _('No default account configured on the cash journal "%s".') % journal.name
            )
        return account

    def _create_delivery_journal_entry(self, delivery_amount):
        """
        Create and immediately post the delivery amount journal entry.

        Debit  → Cash Account (POS Cash Payment Method Journal)
        Credit → Intermediate Account (POS Config)
        """
        config = self.config_id
        company = self.company_id
        currency = self.currency_id

        cash_account = self._get_cash_account()
        intermediate_account = config.delivery_intermediate_account_id
        delivery_journal = config.delivery_journal_id

        # Build the entry label
        opening_date = self.start_at.strftime('%Y-%m-%d') if self.start_at else ''
        ref = _('Deliver Amount From %(pos)s - %(date)s', pos=config.name, date=opening_date)

        move_vals = {
            'journal_id': delivery_journal.id,
            'date': fields.Date.context_today(self),
            'ref': ref,
            'company_id': company.id,
            'currency_id': currency.id,
            'line_ids': [
                # Debit – Cash Account
                (0, 0, {
                    'account_id': cash_account.id,
                    'name': ref,
                    'debit': delivery_amount,
                    'credit': 0.0,
                    'currency_id': currency.id,
                }),
                # Credit – Intermediate Account
                (0, 0, {
                    'account_id': intermediate_account.id,
                    'name': ref,
                    'debit': 0.0,
                    'credit': delivery_amount,
                    'currency_id': currency.id,
                }),
            ],
        }

        move = self.env['account.move'].create(move_vals)
        move.action_post()
        return move

    def _log_delivery_chatter(self, delivery_amount, move=None):
        """Append an audit trail note to the session chatter."""
        currency_symbol = self.currency_id.symbol or ''
        user = self.env.user
        now = fields.Datetime.now()

        if move:
            entry_ref = '<a href="#" data-oe-model="account.move" data-oe-id="{id}">{name}</a>'.format(
                id=move.id, name=move.name or _('Draft')
            )
        else:
            entry_ref = _('No journal entry (amount is zero)')

        body = _(
            '<b>Delivery Amount processed successfully.</b><br/>'
            'Amount: %(symbol)s %(amount).2f<br/>'
            'Processed by: %(user)s<br/>'
            'Journal Entry: %(entry)s<br/>'
            'Date &amp; Time: %(datetime)s',
            symbol=currency_symbol,
            amount=delivery_amount,
            user=user.name,
            entry=entry_ref,
            datetime=fields.Datetime.to_string(now),
        )
        self.message_post(body=body)
