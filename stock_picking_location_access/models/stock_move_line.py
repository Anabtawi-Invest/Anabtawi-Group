from odoo import api, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _check_picking_location_access(self, action_label=None):
        pickings = self.picking_id
        if pickings:
            pickings._check_location_access(action_label)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_picking_location_access(self.env._("add detailed operations on"))
        return lines

    def write(self, vals):
        self._check_picking_location_access(self.env._("edit quantities on"))
        return super().write(vals)

    def unlink(self):
        self._check_picking_location_access(self.env._("remove detailed operations from"))
        return super().unlink()
