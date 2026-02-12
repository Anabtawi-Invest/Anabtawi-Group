import logging

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # =========================================================
    # 1️⃣ ORIGINAL DISCREPANCY DETECTION LOGIC (KEEP THIS)
    # =========================================================
    def _get_transfer_discrepancy_move_vals(self):
        self.ensure_one()

        # Only if truck involved
        if not (self.location_id.is_truck or self.location_dest_id.is_truck):
            return []

        if self.location_dest_id.is_truck and not self.location_id.is_truck:
            truck_location = self.location_dest_id
            stage = "dispatch"
        elif self.location_id.is_truck and not self.location_dest_id.is_truck:
            truck_location = self.location_id
            stage = "receipt"
        else:
            truck_location = self.location_id
            stage = "dispatch"

        vals_list = []

        for move in self.move_ids.filtered(lambda m: m.state != "cancel"):
            picked_qty = move._get_picked_quantity()
            expected_qty = move.product_uom_qty

            if move.product_uom.compare(expected_qty, picked_qty) > 0:
                expected = move.product_uom._compute_quantity(
                    expected_qty, move.product_id.uom_id, round=False
                )
                actual = move.product_uom._compute_quantity(
                    picked_qty, move.product_id.uom_id, round=False
                )

                vals_list.append(
                    {
                        "picking_id": self.id,
                        "product_id": move.product_id.id,
                        "expected_qty": expected,
                        "actual_qty": actual,
                        "difference_qty": expected - actual,
                        "truck_location_id": truck_location.id,
                        "stage": stage,
                    }
                )

        return vals_list

    # =========================================================
    # 2️⃣ OPEN WIZARD AFTER VALIDATION (NOT BEFORE)
    # =========================================================
    def button_validate(self):
        res = super().button_validate()

        # If Odoo returns another wizard (backorder), respect it
        if isinstance(res, dict):
            return res

        done_pickings = self.filtered(
            lambda p: p.state == "done" and p.picking_type_code == "internal"
        )
        if not done_pickings:
            return res

        discrepancy_lines = []
        for picking in done_pickings:
            discrepancy_lines += picking._get_transfer_discrepancy_move_vals()

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

    # =========================================================
    # 3️⃣ SETTLEMENT LOGIC (NO CREATE HERE)
    # =========================================================
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
                    qty = move.product_uom._compute_quantity(
                        move.quantity, move.product_id.uom_id, round=False
                    )
                    Discrepancy.apply_resolution(
                        truck,
                        move.product_id,
                        qty,
                        stage="dispatch",
                        exclude_picking_ids=[picking.id],
                    )
                    truck_locations_to_recompute.add(truck)

            if picking.location_id.is_truck:
                truck = picking.location_id
                for move in done_moves:
                    qty = move.product_uom._compute_quantity(
                        move.quantity, move.product_id.uom_id, round=False
                    )
                    Discrepancy.apply_resolution(
                        truck,
                        move.product_id,
                        qty,
                        stage="receipt",
                        exclude_picking_ids=[picking.id],
                    )
                    truck_locations_to_recompute.add(truck)

        if truck_locations_to_recompute:
            self.env["stock.location"].browse(
                [loc.id for loc in truck_locations_to_recompute]
            )._compute_has_open_discrepancy()

        return res
