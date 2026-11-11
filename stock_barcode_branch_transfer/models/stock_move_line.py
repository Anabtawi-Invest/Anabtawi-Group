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
            if not picking._branch_location_override_enabled():
                continue
            locked_source = picking.barcode_locked_source_location_id
            locked_dest = picking.barcode_locked_dest_location_id
            if locked_source and line.location_id and line.location_id != locked_source:
                raise UserError(
                    picking._branch_location_mismatch_message("source", locked_source)
                )
            if locked_dest and line.location_dest_id and line.location_dest_id != locked_dest:
                raise UserError(
                    picking._branch_location_mismatch_message("dest", locked_dest)
                )

    def _sync_branch_locks_from_vals(self, lines, vals):
        if self.env.context.get("skip_branch_location_check"):
            return
        for line in lines:
            picking = line.picking_id
            if not picking or not picking._branch_location_override_enabled():
                continue
            if "location_id" in vals or not picking.barcode_locked_source_location_id:
                if line.location_id:
                    picking._apply_branch_location_from_line("source", line.location_id)
            if "location_dest_id" in vals or not picking.barcode_locked_dest_location_id:
                if line.location_dest_id:
                    picking._apply_branch_location_from_line("dest", line.location_dest_id)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_branch_locks_from_vals(
            lines,
            {"location_id": True, "location_dest_id": True},
        )
        lines._check_branch_barcode_locations()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {"location_id", "location_dest_id", "picking_id"} & set(vals):
            self._sync_branch_locks_from_vals(self, vals)
            self._check_branch_barcode_locations()
        return res
