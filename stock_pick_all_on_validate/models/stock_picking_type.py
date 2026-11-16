from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    pick_all_on_validate = fields.Boolean(
        string="Pick all lines on validate",
        help="Before the transfer is set to Done, set Picked on every open "
        "line. The quantity already entered on the line is what gets "
        "transferred. Picked stays off until Validate, so reservation is "
        "unchanged. This operation type's backorder setting still decides "
        "what happens to any remaining demand.",
    )
