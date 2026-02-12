import logging

from odoo import _, api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # ---------------------------------------------------------
    # 1️⃣ Open wizard AFTER validation (not before)
    # ---------------------------------------------------------
    def button_validate(self):
        res = super().button_validate()

        # If Odoo returned another wizard (like backorder), keep it
        if isinstance(res, dict):
            return res

        # Only for internal transfers that are already done
        done_pickings = self.filtered(
            lambda p: p.state == "done" and p.picking_type_code == "internal"
        )
        if not done_pickings:
            return res

        discrepancy_lines = []
        for picking in done_pickings:
            lines = picking._get_transfer_discrepancy_move_vals()
            discrepancy_lines += lines

        if not discrepancy_lines:
            return res

        view = self.env.ref(
            "stock_transfer_discrepancy.stock_transfer_discrepancy_wizard_view_form"
        )

        return {
            "name": self.env._("Discrepancy Reason Required"),
            "type": "ir.actions.act_window",
            "res_model": "stock.transfer.discrepancy.wizard",
            "view_mode": "form",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": dict(
                self.env.context,
                default_pick_ids=[(6, 0, done_pickings.ids)],
            ),
        }

    # ---------------------------------------------------------
    # 2️⃣ Keep settlement logic AFTER done (no create here)
    # ---------------------------------------------------------
    def _action_done(self):
        res = super()._action_done()

        Discrepancy = self.env["stock.transfer.discrepancy"]
        truck_locations_to_recompute = set()

        for picking in self.filtered(lambda p: p.picking_type_code == "internal"):
            done_moves = picking.move_ids.filtered(
                lambda m: m.state == "done" and m.product_id
            )
            if not done_moves:
                continue

            if picking.location_dest_id.is_truck:
                truck = picking.location_dest_id
                for move in done_moves:
                    qty_prod_uom = move.product_uom._compute_quantity(
                        move.quantity,
                        move.product_id.uom_id,
                        round=False,
                    )
                    Discrepancy.apply_resolution(
                        truck,
                        move.product_id,
                        qty_prod_uom,
                        stage="dispatch",
                        exclude_picking_ids=[picking.id],
                    )
                    truck_locations_to_recompute.add(truck)

            if picking.location_id.is_truck:
                truck = picking.location_id
                for move in done_moves:
                    qty_prod_uom = move.product_uom._compute_quantity(
                        move.quantity,
                        move.product_id.uom_id,
                        round=False,
                    )
                    Discrepancy.apply_resolution(
                        truck,
                        move.product_id,
                        qty_prod_uom,
                        stage="receipt",
                        exclude_picking_ids=[picking.id],
                    )
                    truck_locations_to_recompute.add(truck)

        if truck_locations_to_recompute:
            self.env["stock.location"].browse(
                [loc.id for loc in truck_locations_to_recompute]
            )._compute_has_open_discrepancy()

        return res
