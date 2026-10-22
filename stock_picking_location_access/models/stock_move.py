from odoo import api, models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _check_picking_location_access(self, action_label=None):
        pickings = self.picking_id
        if pickings:
            pickings._check_location_access(action_label)

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._check_picking_location_access(self.env._("add lines on"))
        return moves

    def write(self, vals):
        self._check_picking_location_access(self.env._("edit lines on"))
        return super().write(vals)

    def unlink(self):
        self._check_picking_location_access(self.env._("remove lines from"))
        return super().unlink()

    def _push_apply(self):
        # Next-hop moves must be creatable while validating the previous transfer
        return super(
            StockMove,
            self.with_context(skip_stock_picking_location_access=True),
        )._push_apply()
