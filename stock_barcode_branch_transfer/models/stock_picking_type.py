from odoo import api, fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    barcode_override_scanned_locations = fields.Boolean(
        string="Override locations from scan",
        help="When source location scanning is mandatory, the first scanned "
        "source and the first scanned destination replace the generated "
        "transfer locations. A later scan must be that same location.",
    )

    @api.onchange("restrict_scan_source_location")
    def _onchange_restrict_scan_source_location_override(self):
        if self.restrict_scan_source_location != "mandatory":
            self.barcode_override_scanned_locations = False

    @api.model_create_multi
    def create(self, vals_list):
        cleaned = []
        for vals in vals_list:
            vals = dict(vals)
            if (
                vals.get("barcode_override_scanned_locations")
                and vals.get("restrict_scan_source_location") != "mandatory"
            ):
                vals["barcode_override_scanned_locations"] = False
            cleaned.append(vals)
        picking_types = super().create(cleaned)
        to_clear = picking_types.filtered(
            lambda picking_type: picking_type.barcode_override_scanned_locations
            and picking_type.restrict_scan_source_location != "mandatory"
        )
        if to_clear:
            super(StockPickingType, to_clear).write(
                {"barcode_override_scanned_locations": False}
            )
        return picking_types

    def write(self, vals):
        vals = dict(vals)
        if (
            "restrict_scan_source_location" in vals
            and vals["restrict_scan_source_location"] != "mandatory"
        ):
            vals["barcode_override_scanned_locations"] = False
        res = super().write(vals)
        to_clear = self.filtered(
            lambda picking_type: picking_type.barcode_override_scanned_locations
            and picking_type.restrict_scan_source_location != "mandatory"
        )
        if to_clear:
            super(StockPickingType, to_clear).write(
                {"barcode_override_scanned_locations": False}
            )
        return res

    def _get_barcode_config(self):
        config = super()._get_barcode_config()
        config["barcode_override_scanned_locations"] = (
            self.barcode_override_scanned_locations
        )
        return config
