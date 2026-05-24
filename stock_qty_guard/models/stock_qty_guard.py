import logging

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_done_qty_in_move_uom(self, move):
        if "quantity" in move._fields:
            return move.quantity or 0.0

        done_total = 0.0
        for line in move.move_line_ids.filtered(lambda ml: ml.state != "cancel"):
            done_total += line.product_uom_id._compute_quantity(line.qty_done, move.product_uom)
        return done_total

    def _check_over_receipt_quantities(self):
        bypass_group = "stock_qty_guard.group_allow_over_receipt_validation_bypass"
        if self.env.user.has_group(bypass_group):
            _logger.warning(
                "Over-receipt check skipped: user '%s' (id=%s) has bypass group '%s'. Pickings=%s",
                self.env.user.login,
                self.env.user.id,
                bypass_group,
                self.mapped("name"),
            )
            return

        incoming_pickings = self.filtered(lambda p: p.picking_type_code == "incoming")
        if not incoming_pickings:
            _logger.warning(
                "Over-receipt check skipped: no incoming pickings in recordset. Pickings=%s, types=%s",
                self.mapped("name"),
                list(set(self.mapped("picking_type_code"))),
            )
            return

        for picking in incoming_pickings:
            violations = []
            for move in picking.move_ids.filtered(lambda m: m.state != "cancel"):
                done_qty = picking._get_done_qty_in_move_uom(move)
                demand_qty = move.product_uom_qty or 0.0
                _logger.warning(
                    "Over-receipt compare on picking '%s': product='%s', demanded=%s %s, received=%s %s",
                    picking.name,
                    move.product_id.display_name,
                    demand_qty,
                    move.product_uom.name,
                    done_qty,
                    move.product_uom.name,
                )
                if float_compare(
                    done_qty,
                    demand_qty,
                    precision_rounding=move.product_uom.rounding,
                ) > 0:
                    violations.append(
                        _(
                            "- %(product)s (Demanded: %(demand)s %(uom)s, Received: %(done)s %(uom)s)",
                            product=move.product_id.display_name,
                            demand=demand_qty,
                            done=done_qty,
                            uom=move.product_uom.name,
                        )
                    )

            if violations:
                _logger.warning(
                    "Over-receipt blocked on picking '%s'. Violations:\n%s",
                    picking.name,
                    "\n".join(violations),
                )
                raise ValidationError(
                    _(
                        "You cannot validate this Receipt because received quantity exceeds demanded quantity:\n%(lines)s",
                        lines="\n".join(violations),
                    )
                )

            _logger.warning(
                "Over-receipt check passed on incoming picking '%s' (no violations).",
                picking.name,
            )

    def button_validate(self):
        self._check_over_receipt_quantities()
        return super().button_validate()
