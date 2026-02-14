import logging

from odoo import _, api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_transfer_discrepancy_move_vals(self):
        """Return list of dicts for moves where actual < expected.

        All quantities are expressed in the product's default UoM.
        """
        self.ensure_one()
        _logger.info(
            "[DISCREPANCY] Checking picking %s (ID: %s) for discrepancies",
            self.name,
            self.id,
        )
        _logger.info(
            "[DISCREPANCY] Source location: %s (ID: %s, is_truck: %s)",
            self.location_id.name,
            self.location_id.id,
            self.location_id.is_truck,
        )
        _logger.info(
            "[DISCREPANCY] Dest location: %s (ID: %s, is_truck: %s)",
            self.location_dest_id.name,
            self.location_dest_id.id,
            self.location_dest_id.is_truck,
        )

        # Only apply discrepancy flow when truck is the SOURCE location.
        if not self.location_id.is_truck:
            _logger.warning(
                "[DISCREPANCY] Skipping: source is not truck. Source is_truck=%s, Dest is_truck=%s",
                self.location_id.is_truck,
                self.location_dest_id.is_truck,
            )
            return []

        truck_location = self.location_id
        stage = "receipt"
        _logger.info(
            "[DISCREPANCY] Truck found at SOURCE: %s (stage: receipt)",
            truck_location.name,
        )

        vals_list = []
        moves_checked = 0
        for move in self.move_ids.filtered(lambda m: m.state != "cancel"):
            moves_checked += 1
            picked_qty = move._get_picked_quantity()
            expected_qty = move.product_uom_qty
            _logger.info(
                "[DISCREPANCY] Move %s (Product: %s): Expected=%s, Picked=%s",
                move.id,
                move.product_id.name,
                expected_qty,
                picked_qty,
            )

            if move.product_uom.compare(expected_qty, picked_qty) > 0:
                expected = move.product_uom._compute_quantity(
                    expected_qty, move.product_id.uom_id, round=False
                )
                actual = move.product_uom._compute_quantity(
                    picked_qty, move.product_id.uom_id, round=False
                )
                _logger.info(
                    "[DISCREPANCY] ✓ DISCREPANCY FOUND! Product: %s, Expected=%s, Actual=%s, Diff=%s",
                    move.product_id.name,
                    expected,
                    actual,
                    expected - actual,
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
            else:
                _logger.info(
                    "[DISCREPANCY] No discrepancy for move %s (Product: %s)",
                    move.id,
                    move.product_id.name,
                )

        _logger.info(
            "[DISCREPANCY] Total moves checked: %s, Discrepancies found: %s",
            moves_checked,
            len(vals_list),
        )
        return vals_list

    def _pre_action_done_hook(self):
        # Open our wizard before Odoo's backorder wizard, but only once.
        _logger.info(
            "[DISCREPANCY] _pre_action_done_hook called for pickings: %s",
            self.mapped("name"),
        )
        _logger.info(
            "[DISCREPANCY] Context skip_transfer_discrepancy_wizard: %s",
            self.env.context.get("skip_transfer_discrepancy_wizard"),
        )

        if not self.env.context.get("skip_transfer_discrepancy_wizard"):
            discrepancy_lines = []
            for picking in self:
                _logger.info(
                    "[DISCREPANCY] Checking picking %s (ID: %s) for discrepancies",
                    picking.name,
                    picking.id,
                )
                lines = picking._get_transfer_discrepancy_move_vals()
                discrepancy_lines += lines
                _logger.info(
                    "[DISCREPANCY] Picking %s returned %s discrepancy lines",
                    picking.name,
                    len(lines),
                )

            _logger.info(
                "[DISCREPANCY] Total discrepancy lines collected: %s",
                len(discrepancy_lines),
            )

            if discrepancy_lines:
                _logger.info(
                    "[DISCREPANCY] ✓ Opening wizard with %s discrepancy lines",
                    len(discrepancy_lines),
                )
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
                        default_pick_ids=[(6, 0, self.ids)],
                    ),
                }
            else:
                _logger.warning(
                    "[DISCREPANCY] ✗ No discrepancy lines found. Wizard will NOT open."
                )
        else:
            _logger.info(
                "[DISCREPANCY] Skipping wizard (skip_transfer_discrepancy_wizard in context)"
            )

        return super()._pre_action_done_hook()

    def _action_done(self):
        res = super()._action_done()
        # Settlement via internal transfers when truck is SOURCE only.
        # Moving OUT OF a truck resolves RECEIPT discrepancies.
        Discrepancy = self.env["stock.transfer.discrepancy"]
        truck_locations_to_recompute = set()
        for picking in self.filtered(lambda p: p.picking_type_code == "internal"):
            done_moves = picking.move_ids.filtered(lambda m: m.state == "done" and m.product_id)
            if not done_moves:
                continue

            if picking.location_id.is_truck:
                truck = picking.location_id
                for move in done_moves:
                    qty_prod_uom = move.product_uom._compute_quantity(
                        move.quantity, move.product_id.uom_id, round=False
                    )
                    Discrepancy.apply_resolution(
                        truck, move.product_id, qty_prod_uom, stage="receipt", exclude_picking_ids=[picking.id]
                    )
                    truck_locations_to_recompute.add(truck)

        # Trigger recompute of has_open_discrepancy on all affected truck locations
        if truck_locations_to_recompute:
            location_ids = [loc.id for loc in truck_locations_to_recompute]
            self.env["stock.location"].browse(location_ids)._compute_has_open_discrepancy()

        return res

    @api.onchange("picking_type_id", "location_id", "location_dest_id")
    def _onchange_picking_type_id_discrepancy_truck_domain(self):
        """Block selecting trucks with open discrepancies on internal transfers."""
        _logger.info(
            "[DISCREPANCY DOMAIN] _onchange called. picking_type_code=%s",
            self.picking_type_code,
        )
        if self.picking_type_code != "internal":
            _logger.info(
                "[DISCREPANCY DOMAIN] Not internal transfer, skipping domain restriction"
            )
            return {}
        source_domain = [
            ("usage", "=", "internal"),
            "|",
            ("is_truck", "=", False),
            ("has_open_discrepancy", "=", False),
        ]
        dest_domain = [("usage", "=", "internal")]
        _logger.info(
            "[DISCREPANCY DOMAIN] Applying source domain on location_id only: %s",
            source_domain,
        )
        
        warning_msg = None
        if self.location_id:
            _logger.info(
                "[DISCREPANCY DOMAIN] Current location_id: %s (ID: %s, is_truck: %s, has_open_discrepancy: %s)",
                self.location_id.name,
                self.location_id.id,
                self.location_id.is_truck,
                self.location_id.has_open_discrepancy,
            )
            if self.location_id.is_truck and self.location_id.has_open_discrepancy:
                warning_msg = _(
                    "Cannot use truck location '%s' as source location: it has open discrepancies. "
                    "Please settle the discrepancies first or choose another location.",
                    self.location_id.name,
                )
                _logger.warning(
                    "[DISCREPANCY DOMAIN] Warning: Source location %s has open discrepancy",
                    self.location_id.name,
                )
                # Clear the location to force user to choose another one
                self.location_id = False
        
        result = {"domain": {"location_id": source_domain, "location_dest_id": dest_domain}}
        if warning_msg:
            result["warning"] = {
                "title": _("Truck Location with Open Discrepancy"),
                "message": warning_msg,
            }
        return result

    @api.constrains("location_id", "location_dest_id", "picking_type_code")
    def _check_truck_open_discrepancy(self):
        """Prevent using trucks with open discrepancies in internal transfers."""
        for picking in self:
            if picking.picking_type_code != "internal":
                continue

            if picking.location_id.is_truck and picking.location_id.has_open_discrepancy:
                _logger.warning(
                    "[DISCREPANCY DOMAIN] Constraint violation: Source location %s (ID: %s) is truck with open discrepancy",
                    picking.location_id.name,
                    picking.location_id.id,
                )
                raise ValidationError(
                    _(
                        "Cannot use truck location '%s' as source location: it has open discrepancies. "
                        "Please settle the discrepancies first or choose another location.",
                        picking.location_id.name,
                    )
                )

    @api.constrains("location_id", "location_dest_id", "picking_type_code")
    def _check_truck_open_discrepancy(self):
        """Prevent using trucks with open discrepancies in internal transfers."""
        for picking in self:
            if picking.picking_type_code != "internal":
                continue

            if picking.location_id.is_truck and picking.location_id.has_open_discrepancy:
                _logger.warning(
                    "[DISCREPANCY DOMAIN] Constraint violation: Source location %s (ID: %s) is truck with open discrepancy",
                    picking.location_id.name,
                    picking.location_id.id,
                )
                raise ValidationError(
                    _(
                        "Cannot use truck location '%s' as source location: it has open discrepancies. "
                        "Please settle the discrepancies first or choose another location.",
                        picking.location_id.name,
                    )
                )

