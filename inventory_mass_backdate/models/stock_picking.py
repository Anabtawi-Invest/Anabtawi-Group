from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    original_date_done = fields.Datetime(
        string='Original Date Done',
        readonly=True,
        copy=False,
        help='Completion date recorded on this transfer before the last '
             'mass backdate was applied.',
    )
    backdated_by = fields.Many2one(
        'res.users',
        string='Backdated By',
        readonly=True,
        copy=False,
    )
    backdate_reason = fields.Char(
        string='Backdate Reason',
        readonly=True,
        copy=False,
    )

    def action_open_backdate_wizard(self):
        """Open the mass backdate wizard pre-filled with this selection."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mass Backdate',
            'res_model': 'stock.backdate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_filter_domain': str([('id', 'in', self.ids)]),
            },
        }
