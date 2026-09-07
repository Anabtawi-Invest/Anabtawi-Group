from odoo import fields, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    counted_date = fields.Datetime(
        string='Counted On',
        copy=False,
        help="Actual date the physical count was taken. When you run "
             "'Apply Backdated Count', the inventory adjustment, its stock "
             "moves and the accounting entry are all dated to this date, and "
             "the counted quantity is compared against the on-hand quantity "
             "as it was on this date (not today) so movements between the "
             "count date and today are preserved.",
    )
