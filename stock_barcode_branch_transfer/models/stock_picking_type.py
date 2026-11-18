from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    barcode_override_scanned_locations = fields.Boolean(
        string="Override locations from scan",
        help="When enabled, scanning this operation type creates a transfer, "
        "then you must scan the source location, then the destination "
        "location. Those locations are assigned on the transfer before "
        "you scan products. Scanning a different source or destination "
        "later is blocked.",
    )

    def _get_barcode_config(self):
        config = super()._get_barcode_config()
        config["barcode_override_scanned_locations"] = (
            self.barcode_override_scanned_locations
        )
        return config
