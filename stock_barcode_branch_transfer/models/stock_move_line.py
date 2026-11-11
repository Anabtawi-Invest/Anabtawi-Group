from odoo import api, models
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _check_branch_barcode_locations(self):
        if self.env.context.get("skip_branch_location_check"):
            return
        for line in self:
            picking = line.picking_id
            if not picking or picking.state in ("done", "cancel"):
                continue
            picking_type = picking.picking_type_id
            if (
                not picking_type.barcode_override_scanned_locations
                or picking_type.restrict_scan_source_location != "mandatory"
            ):
                continue
            locked_source = picking.barcode_locked_source_location_id
            locked_dest = picking.barcode_locked_dest_location_id
            if locked_source and line.location_id and line.location_id != locked_source:
                raise UserError(picking._branch_location_mismatch_message("source", locked_source))
            if locked_dest and line.location_dest_id and line.location_dest_id != locked_dest:
                raise UserError(picking._branch_location_mismatch_message("dest", locked_dest))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_branch_barcode_locations()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {"location_id", "location_dest_id", "picking_id"} & set(vals):
            self._check_branch_barcode_locations()
        return res
