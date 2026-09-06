import ast

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockBackdateWizard(models.TransientModel):
    _name = 'stock.backdate.wizard'
    _description = 'Mass Backdate Stock Transfers'

    new_date = fields.Datetime(
        string='New Date',
        required=True,
        default=fields.Datetime.now,
    )
    reason = fields.Char(
        string='Reason for Backdate',
        required=True,
    )
    recalculate_valuation = fields.Boolean(
        string='Recalculate Inventory Valuation',
        help='Also update the date of the posted accounting entries linked '
             'to the backdated stock moves (via their valuation layers). '
             'Entries with reconciled lines are left untouched.',
    )
    filter_domain = fields.Char(
        string='Transfers Filter Domain',
        default="[('state', '=', 'done')]",
        help="Standard Odoo domain, e.g. [('state', '=', 'done'), "
             "('picking_type_code', '=', 'outgoing')]. Only transfers in "
             "the 'Done' state are ever processed.",
    )
    matched_count = fields.Integer(
        string='Transfers to Backdate',
        compute='_compute_matched_count',
        help="Number of 'Done' transfers matching the filter domain that "
             "will be backdated when you apply.",
    )

    @api.depends('filter_domain')
    def _compute_matched_count(self):
        for wizard in self:
            try:
                domain = wizard._get_domain()
            except UserError:
                wizard.matched_count = 0
                continue
            wizard.matched_count = self.env['stock.picking'].search_count(
                domain + [('state', '=', 'done')]
            )

    def _get_domain(self):
        self.ensure_one()
        raw = (self.filter_domain or '').strip() or '[]'
        try:
            domain = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            raise UserError(_(
                'Invalid domain: it must be a valid Python list of tuples, '
                'e.g. [(\'state\', \'=\', \'done\')].'
            ))
        if not isinstance(domain, list):
            raise UserError(_('The transfers filter domain must be a list of tuples.'))
        return domain

    def action_apply_backdate(self):
        self.ensure_one()
        domain = self._get_domain()
        pickings = self.env['stock.picking'].search(domain + [('state', '=', 'done')])
        if not pickings:
            raise UserError(_(
                "No stock transfers found in the 'Done' state matching this domain."
            ))

        moves_to_update = self.env['stock.move']
        for picking in pickings:
            picking.write({
                'original_date_done': picking.date_done,
                'backdated_by': self.env.uid,
                'backdate_reason': self.reason,
                'date_done': self.new_date,
            })
            moves_to_update |= picking.move_ids

        if moves_to_update:
            moves_to_update.write({'date': self.new_date})
            moves_to_update.mapped('move_line_ids').write({'date': self.new_date})

        if self.recalculate_valuation and moves_to_update:
            # The accounting entry for a stock move is not linked directly;
            # it goes through the move's valuation layer(s).
            valuation_layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', 'in', moves_to_update.ids),
                ('account_move_id', '!=', False),
            ])
            journal_entries = valuation_layers.account_move_id.filtered(
                lambda m: m.state == 'posted'
            )
            for entry in journal_entries:
                if any(line.reconciled for line in entry.line_ids):
                    continue
                entry.write({'date': self.new_date})

        return {'type': 'ir.actions.act_window_close'}
