from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools import float_compare
from odoo.tools.misc import format_date


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    split_murabaha_interest = fields.Boolean(
        string='Separate Murabaha Entry',
        help='If enabled, Confirm posts the installment at full payment amount on due ST, '
             'and posts murabaha/interest on a separate short-term liability account.',
        tracking=True,
    )
    murabaha_liability_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Murabaha Liability Account',
        tracking=True,
        domain="[('account_type', '=', 'liability_current')]",
        help='Short-term liability account credited with the murabaha/interest amount.',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        tracking=True,
        check_company=True,
        help='Applied at 100%% on murabaha/expense journal items when confirming the loan.',
    )
    bayaan = fields.Char(
        string='Statement',
        tracking=True,
        help='Used as journal item label together with the period date (MM/y) when confirming the loan.',
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        wanted = {'murabaha_liability_account_id', 'split_murabaha_interest', 'analytic_account_id'}
        if not wanted.intersection(fields_list):
            return values
        previous_loan = self.search([
            ('company_id', '=', self.env.company.id),
            '|',
            ('murabaha_liability_account_id', '!=', False),
            ('analytic_account_id', '!=', False),
        ], limit=1)
        if previous_loan:
            if previous_loan.split_murabaha_interest and previous_loan.murabaha_liability_account_id:
                values.setdefault('split_murabaha_interest', True)
                values.setdefault('murabaha_liability_account_id', previous_loan.murabaha_liability_account_id.id)
            if previous_loan.analytic_account_id:
                values.setdefault('analytic_account_id', previous_loan.analytic_account_id.id)
        return values

    def _get_loan_analytic_distribution(self):
        self.ensure_one()
        if not self.analytic_account_id:
            return False
        return {str(self.analytic_account_id.id): 100.0}

    def _get_bayaan_line_label(self, period_label):
        """Return '{bayaan} {MM/y}' or False when bayaan is empty."""
        self.ensure_one()
        if not self.bayaan:
            return False
        return f"{self.bayaan} {period_label}"

    def _apply_analytic_on_expense_lines(self):
        """Checkbox OFF: analytic 100% on expense account lines of generated moves."""
        for loan in self:
            distribution = loan._get_loan_analytic_distribution()
            if not distribution or not loan.expense_account_id:
                continue
            expense_lines = loan.line_ids.generated_move_ids.line_ids.filtered(
                lambda line: line.account_id == loan.expense_account_id
            )
            if expense_lines:
                expense_lines.write({'analytic_distribution': distribution})

    def _apply_bayaan_on_payment_move_lines(self):
        """Checkbox OFF: bayaan + date as label on all lines of the Principal & Interest entry."""
        for loan in self:
            if not loan.bayaan:
                continue
            payment_moves = loan.line_ids.generated_move_ids.filtered(lambda m: m.is_loan_payment_move)
            for move in payment_moves:
                period_label = format_date(self.env, move.generating_loan_line_id.date, date_format='MM/y')
                label = loan._get_bayaan_line_label(period_label)
                if label and move.line_ids:
                    move.line_ids.write({'name': label})

    def action_confirm(self):
        normal_loans = self.filtered(lambda loan: not loan.split_murabaha_interest)
        split_loans = self - normal_loans
        if normal_loans:
            super(AccountLoan, normal_loans).action_confirm()
            normal_loans._apply_analytic_on_expense_lines()
            normal_loans._apply_bayaan_on_payment_move_lines()
        for loan in split_loans:
            loan._action_confirm_with_murabaha_split()

    def _action_confirm_with_murabaha_split(self):
        self.ensure_one()
        loan = self

        if not loan.name:
            raise UserError(_("The loan name should be set."))
        if loan.is_wrong_date:
            raise UserError(_("The loan date should be earlier than the loan lines date."))
        if float_compare(loan.amount_borrowed_difference, 0.0, precision_rounding=loan.currency_id.rounding) != 0:
            raise UserError(_(
                "The loan amount %(loan_amount)s should be equal to the sum of the principals: %(principal_sum)s (difference %(principal_difference)s)",
                loan_amount=loan.currency_id.format(loan.amount_borrowed),
                principal_sum=loan.currency_id.format(sum(loan.line_ids.mapped('principal'))),
                principal_difference=loan.currency_id.format(loan.amount_borrowed_difference),
            ))
        if float_compare(loan.interest_difference, 0.0, precision_rounding=loan.currency_id.rounding) != 0:
            raise UserError(_("The loan interest should be equal to the sum of the loan lines interest."))
        if loan.duration_difference != 0:
            raise UserError(_("The loan duration should be equal to the number of loan lines."))
        if not loan.long_term_account_id or not loan.short_term_account_id or not loan.expense_account_id:
            raise UserError(_("The loan accounts should be set."))
        if not loan.journal_id:
            raise UserError(_("The loan journal should be set."))
        if not loan.murabaha_liability_account_id:
            raise UserError(_("Please set the Murabaha Liability Account before confirming."))

        analytic_distribution = loan._get_loan_analytic_distribution()
        payment_moves_values = []
        murabaha_moves_values = []
        reclassification_moves_values = []
        reclassification_reversed_moves_values = []

        for i, line in enumerate(loan.line_ids):
            if loan.skip_until_date and line.date < loan.skip_until_date:
                continue

            period_label = format_date(self.env, line.date, date_format='MM/y')
            move_date = line.date + relativedelta(day=31)
            bayaan_label = loan._get_bayaan_line_label(period_label)

            principal_name = bayaan_label or f"{loan.name} - {_('Principal')} {period_label}"
            due_name = bayaan_label or (
                f"{loan.name} - {_('Due')} {period_label} "
                f"({_('Principal')} {loan.currency_id.format(line.principal)} + {_('Interest')} {loan.currency_id.format(line.interest)})"
            )
            murabaha_name = bayaan_label or f"{loan.name} - {_('Murabaha')} {period_label}"
            murabaha_due_name = bayaan_label or f"{loan.name} - {_('Murabaha Due')} {period_label}"

            # Full payment amount on due installments (principal + interest)
            payment_moves_values.append({
                'company_id': loan.company_id.id,
                'auto_post': 'at_date',
                'generating_loan_line_id': line.id,
                'is_loan_payment_move': True,
                'date': move_date,
                'journal_id': loan.journal_id.id,
                'ref': f"{loan.name} - {_('Principal & Interest')} {period_label}",
                'line_ids': [
                    Command.create({
                        'account_id': loan.long_term_account_id.id,
                        'debit': line.payment,
                        'name': principal_name,
                    }),
                    Command.create({
                        'account_id': loan.short_term_account_id.id,
                        'credit': line.payment,
                        'name': due_name,
                    }),
                ],
            })

            # Separate murabaha / interest entry — analytic on both lines when set
            if float_compare(line.interest, 0.0, precision_rounding=loan.currency_id.rounding) > 0:
                expense_line_vals = {
                    'account_id': loan.expense_account_id.id,
                    'debit': line.interest,
                    'name': murabaha_name,
                }
                murabaha_liability_line_vals = {
                    'account_id': loan.murabaha_liability_account_id.id,
                    'credit': line.interest,
                    'name': murabaha_due_name,
                }
                if analytic_distribution:
                    expense_line_vals['analytic_distribution'] = analytic_distribution
                    murabaha_liability_line_vals['analytic_distribution'] = analytic_distribution
                murabaha_moves_values.append({
                    'company_id': loan.company_id.id,
                    'auto_post': 'at_date',
                    'generating_loan_line_id': line.id,
                    'is_loan_payment_move': False,
                    'date': move_date,
                    'journal_id': loan.journal_id.id,
                    'ref': f"{loan.name} - {_('Murabaha')} {period_label}",
                    'line_ids': [
                        Command.create(expense_line_vals),
                        Command.create(murabaha_liability_line_vals),
                    ],
                })

            if line == loan.line_ids[-1]:
                break

            next_lines = loan.line_ids[i + 1: i + 13]
            from_date = format_date(self.env, next_lines[0].date, date_format='MM/y')
            to_date = format_date(self.env, next_lines[-1].date, date_format='MM/y')
            common_reclassification_values = {
                'company_id': loan.company_id.id,
                'auto_post': 'at_date',
                'generating_loan_line_id': line.id,
                'is_loan_payment_move': False,
                'journal_id': loan.journal_id.id,
            }
            # Use full payment (principal + interest) to match loan liability opened at P+I
            payment_sum = sum(next_lines.mapped('payment'))
            reclassification_moves_values.append({
                **common_reclassification_values,
                'date': move_date,
                'ref': f"{loan.name} - {_('Reclassification LT - ST')} {from_date} to {to_date}",
                'line_ids': [
                    Command.create({
                        'account_id': loan.long_term_account_id.id,
                        'debit': payment_sum,
                        'name': f"{loan.name} - {_('Reclassification LT - ST')} {from_date} to {to_date} (To {loan.short_term_account_id.code})",
                    }),
                    Command.create({
                        'account_id': loan.short_term_account_id.id,
                        'credit': payment_sum,
                        'name': f"{loan.name} - {_('Reclassification LT - ST')} {from_date} to {to_date} (From {loan.long_term_account_id.code})",
                    }),
                ],
            })
            reclassification_reversed_moves_values.append({
                **common_reclassification_values,
                'date': move_date + relativedelta(days=1),
                'ref': f"{loan.name} - {_('Reversal reclassification LT - ST')} {from_date} to {to_date}",
                'line_ids': [
                    Command.create({
                        'account_id': loan.long_term_account_id.id,
                        'credit': payment_sum,
                        'name': f"{loan.name} - {_('Reversal reclassification LT - ST')} {from_date} to {to_date} (To {loan.short_term_account_id.code})",
                    }),
                    Command.create({
                        'account_id': loan.short_term_account_id.id,
                        'debit': payment_sum,
                        'name': f"{loan.name} - {_('Reversal reclassification LT - ST')} {from_date} to {to_date} (From {loan.long_term_account_id.code})",
                    }),
                ],
            })

        def post_moves(moves):
            moves.filtered(lambda m: m.date <= fields.Date.context_today(self)).action_post()

        payment_moves = self.env['account.move'].create(payment_moves_values)
        murabaha_moves = self.env['account.move'].create(murabaha_moves_values) if murabaha_moves_values else self.env['account.move']
        reclassification_moves = self.env['account.move'].create(reclassification_moves_values)
        reclassification_reversed_moves = self.env['account.move'].create(reclassification_reversed_moves_values)
        all_moves = payment_moves | murabaha_moves | reclassification_moves | reclassification_reversed_moves
        post_moves(all_moves)

        for reclassification_move, reclassification_reversed_move in zip(reclassification_moves, reclassification_reversed_moves):
            reclassification_reversed_move.reversed_entry_id = reclassification_move
            reclassification_reversed_move.message_post(
                body=_('This entry has been reversed from %s', reclassification_move._get_html_link())
            )

        bodies = {}
        for move, reverse in zip(reclassification_moves, reclassification_reversed_moves):
            bodies[move.id] = _('This entry has been %s', reverse._get_html_link(title=_("reversed")))
        reclassification_moves._message_log_batch(bodies=bodies)

        if any(m.state != 'posted' for m in all_moves):
            loan.state = 'running'
