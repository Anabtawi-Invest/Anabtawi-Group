# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


# ==========================================================
# Operation Type Flag (per picking type, NOT global)
# ==========================================================
class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    block_negative_stock = fields.Boolean(
        string="Block Negative Stock (Outgoing)",
        help=(
            "If enabled, validating an outgoing/internal transfer will be blocked "
            "when it would create negative stock.\n\n"
            "IMPORTANT:\n"
            "- Procurement moves (Purchase / Manufacturing / Replenishment) are NOT blocked.\n"
            "- Only manual outgoing/internal validations are checked."
        ),
        default=False,
    )


# ==========================================================
# Stock Picking Validation Logic (Odoo 19 safe)
# ==========================================================
class StockPicking(models.Model):
    _inherit = "stock.picking"

    # ------------------------------------------------------
    # Reliable procurement detection for Odoo 19
    # ------------------------------------------------------
    def _nsb_move_is_procurement_safe(self, move, picking):
        """
        Return True if this move is procurement-related and MUST NOT be blocked.
        This logic is Odoo 19–safe and avoids false positives.
        """

        # 1) Purchase flows (PO, Dropship, etc.)
        if move.purchase_line_id:
            return True

        # 2) Manufacturing flows (finished goods or raw materials)
        if move.production_id or move.raw_material_production_id:
            return True

        # 3) Replenishment / MTO / Rules
        # In Odoo 19, origin is the most reliable indicator
        if picking.origin:
            origin = picking.origin.upper()
            if any(key in origin for key in ("PO", "MO", "OP", "WH", "MTO")):
                return True

        return False

    # ------------------------------------------------------
    # Negative stock check (scoped, safe, non-global)
    # ------------------------------------------------------
    def _nsb_check_negative_stock(self):
        Quant = self.env["stock.quant"]

        for picking in self:
            picking_type = picking.picking_type_id
            if not picking_type or not picking_type.block_negative_stock:
                continue

            for move in picking.move_ids:
                # Skip irrelevant states
                if move.state in ("done", "cancel"):
                    continue

                # ONLY outgoing from internal locations
                if move.location_id.usage != "internal":
                    continue

                # Procurement must NEVER be blocked
                if self._nsb_move_is_procurement_safe(move, picking):
                    continue

                # Quantity to validate
                qty = move.quantity_done or move.product_uom_qty
                if not qty:
                    continue

                # Normalize to product UoM
                qty_product_uom = move.product_uom._compute_quantity(
                    qty, move.product_id.uom_id
                )

                # Available quantity in source location
                available = Quant._get_available_quantity(
                    move.product_id,
                    move.location_id,
                    strict=True,
                )

                # Block ONLY if this validation would cause negative stock
                if float_compare(
                    available,
                    qty_product_uom,
                    precision_rounding=move.product_id.uom_id.rounding,
                ) < 0:
                    raise UserError(_(
                        "Negative stock is not allowed for this operation.\n\n"
                        "Operation Type: %(op)s\n"
                        "Product: %(product)s\n"
                        "Source Location: %(location)s\n"
                        "Available Quantity: %(available)s\n"
                        "Required Quantity: %(required)s\n\n"
                        "Note:\n"
                        "- Procurement (Purchase / Manufacturing / Replenishment) is NOT blocked.\n"
                        "- This restriction applies only to manual outgoing/internal operations."
                    ) % {
                        "op": picking_type.display_name,
                        "product": move.product_id.display_name,
                        "location": move.location_id.display_name,
                        "available": available,
                        "required": qty_product_uom,
                    })

    # ------------------------------------------------------
    # Correct hook point (validation only)
    # ------------------------------------------------------
    def button_validate(self):
        # Check BEFORE Odoo processes the picking
        self._nsb_check_negative_stock()
        return super().button_validate()
