import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _pre_action_done_hook(self):
        # ✅ لا تفتح wizard قبل الإتمام للـ internal transfers
        if any(p.picking_type_code == "internal" for p in self):
            return super()._pre_action_done_hook()

        # (اترك كودك الحالي كما هو لباقي الأنواع إن رغبت)
        return super()._pre_action_done_hook()

    def _action_done(self):
        res = super()._action_done()

        Discrepancy = self.env["stock.transfer.discrepancy"].sudo()
        truck_locations_to_recompute = set()

        # ✅ بعد ما صار picking = done: أنشئ discrepancy للـ internal transfers
        for picking in self.filtered(lambda p: p.picking_type_code == "internal" and p.state == "done"):
            if not (picking.location_id.is_truck or picking.location_dest_id.is_truck):
                continue

            # تحديد truck + stage (نفس منطقك)
            if picking.location_dest_id.is_truck and not picking.location_id.is_truck:
                truck_location = picking.location_dest_id
                stage = "dispatch"
            elif picking.location_id.is_truck and not picking.location_dest_id.is_truck:
                truck_location = picking.location_id
                stage = "receipt"
            else:
                truck_location = picking.location_id
                stage = "dispatch"

            for move in picking.move_ids.filtered(lambda m: m.state == "done" and m.product_id):
                expected = move.product_uom._compute_quantity(
                    move.product_uom_qty, move.product_id.uom_id, round=False
                )
                actual = move.product_uom._compute_quantity(
                    move.quantity, move.product_id.uom_id, round=False
                )

                if float_compare(expected, actual, precision_rounding=move.product_id.uom_id.rounding) > 0:
                    # منع التكرار لو صار re-run لأي سبب
                    exists = Discrepancy.search_count([
                        ("picking_id", "=", picking.id),
                        ("product_id", "=", move.product_id.id),
                        ("truck_location_id", "=", truck_location.id),
                        ("stage", "=", stage),
                    ])
                    if exists:
                        continue

                    Discrepancy.create({
                        "date": picking.date_done or fields.Datetime.now(),
                        "picking_id": picking.id,
                        "product_id": move.product_id.id,
                        "expected_qty": expected,
                        "actual_qty": actual,
                        "difference_qty": expected - actual,
                        "truck_location_id": truck_location.id,
                        "stage": stage,
                    })
                    truck_locations_to_recompute.add(truck_location)

        if truck_locations_to_recompute:
            self.env["stock.location"].browse([l.id for l in truck_locations_to_recompute])._compute_has_open_discrepancy()

        return res
