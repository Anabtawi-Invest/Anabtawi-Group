from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


class StockTransferDiscrepancy(models.Model):
    _name = "stock.transfer.discrepancy"
    _description = "Stock Transfer Discrepancy"
    _order = "date desc, id desc"

    picking_id = fields.Many2one(
        "stock.picking",
        string="Transfer",
        required=True,
        index=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        index=True,
    )
    expected_qty = fields.Float(string="Expected Qty", required=True, digits="Product Unit")
    actual_qty = fields.Float(string="Actual Qty", required=True, digits="Product Unit")
    difference_qty = fields.Float(
        string="Difference Qty",
        compute="_compute_difference_qty",
        store=True,
        digits="Product Unit",
    )
    resolved_qty = fields.Float(string="Resolved Qty", default=0.0, digits="Product Unit")

    reason = fields.Text(string="Reason", required=True)
    stage = fields.Selection(
        [
            ("dispatch", "Dispatch"),
            ("receipt", "Receipt"),
        ],
        string="Stage",
        required=True,
        index=True,
    )
    truck_location_id = fields.Many2one(
        "stock.location",
        string="Truck Location",
        required=True,
        index=True,
        ondelete="restrict",
        domain=[("usage", "=", "internal")],
    )
    state = fields.Selection(
        [("open", "Open"), ("settled", "Settled")],
        string="State",
        default="open",
        required=True,
        index=True,
    )
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Responsible User",
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    date = fields.Datetime(
        string="Date",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    company_id = fields.Many2one(related="picking_id.company_id", store=True, readonly=True)

    @api.depends("expected_qty", "actual_qty")
    def _compute_difference_qty(self):
        for rec in self:
            rec.difference_qty = (rec.expected_qty or 0.0) - (rec.actual_qty or 0.0)

    @api.model
    def apply_resolution(self, truck_location, product, qty_in_product_uom, stage=None, exclude_picking_ids=None):
        """Apply a settlement quantity on open discrepancies for a truck/product.

        - qty_in_product_uom: quantity expressed in product default UoM.
        - stage: optional ('dispatch'/'receipt') to resolve only that stage.
        - exclude_picking_ids: optional list of pickings to exclude (e.g. current picking being processed).
        """
        if not truck_location or not product:
            return
        if not qty_in_product_uom:
            print(222,qty_in_product_uom)
            return

        domain = [
            ("truck_location_id", "=", truck_location.id),
            ("product_id", "=", product.id),
            ("state", "=", "open"),
        ]
        if stage:
            domain.append(("stage", "=", stage))
        if exclude_picking_ids:
            domain.append(("picking_id", "not in", exclude_picking_ids))

        # Debug: Check all open discrepancies for this truck/product
        all_open = self.sudo().search([
            ("truck_location_id", "=", truck_location.id),
            ("product_id", "=", product.id),
            ("state", "=", "open"),
        ])
        
        # Debug: Check ALL open discrepancies in database (for debugging)
        all_open_all = self.sudo().search([("state", "=", "open")])
        
        print("=== DEBUG apply_resolution ===")
        print(f"Truck Location ID: {truck_location.id}, Name: {truck_location.name}")
        print(f"Product ID: {product.id}, Name: {product.name}")
        print(f"Stage filter: {stage}")
        print(f"Qty to resolve: {qty_in_product_uom}")
        print(f"All open discrepancies (no stage filter): {len(all_open)}")
        for disc in all_open:
            print(f"  - Disc ID {disc.id}: stage={disc.stage}, truck={disc.truck_location_id.name}, product={disc.product_id.name}, state={disc.state}")
        print(f"Domain: {domain}")
        print(f"\n=== ALL OPEN DISCREPANCIES IN DB (for debugging) ===")
        print(f"Total open discrepancies: {len(all_open_all)}")
        for disc in all_open_all:
            print(f"  - Disc ID {disc.id}: stage={disc.stage}, truck={disc.truck_location_id.name if disc.truck_location_id else 'EMPTY'}, product={disc.product_id.name}, state={disc.state}, expected={disc.expected_qty}, actual={disc.actual_qty}, diff={disc.difference_qty}")
        print("=== END DEBUG ===")

        # Oldest first
        discrepancies = self.sudo().search(domain, order="date asc, id asc")
        print(f"Found discrepancies after search: {len(discrepancies)}")
        for disc in discrepancies:
            print(f"  - Matched Disc ID {disc.id}: stage={disc.stage}")
        print("=== END DEBUG ===")
        
        remaining_qty = qty_in_product_uom
        for disc in discrepancies:
            before = disc.resolved_qty
            disc._apply_resolution(remaining_qty, skip_recompute=True)
            applied = (disc.resolved_qty or 0.0) - (before or 0.0)
            remaining_qty -= applied
            if float_compare(remaining_qty, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                break

        # Trigger recompute once at the end for better performance
        if discrepancies:
            truck_location._compute_has_open_discrepancy()

    def _apply_resolution(self, qty_in_product_uom, skip_recompute=False):
        """Allocate resolution quantity to this discrepancy and update state.
        
        - skip_recompute: if True, don't trigger recompute (will be done in batch at the end).
        """
        self.ensure_one()
        if self.state != "open":
            return
        rounding = self.product_id.uom_id.rounding
        remaining = max((self.difference_qty or 0.0) - (self.resolved_qty or 0.0), 0.0)
        if float_compare(remaining, 0.0, precision_rounding=rounding) <= 0:
            self.sudo().write({"state": "settled"})
            if not skip_recompute and self.truck_location_id:
                self.truck_location_id._compute_has_open_discrepancy()
            return

        to_apply = min(qty_in_product_uom, remaining)
        if float_compare(to_apply, 0.0, precision_rounding=rounding) <= 0:
            return
        new_resolved = (self.resolved_qty or 0.0) + to_apply
        vals = {"resolved_qty": new_resolved}
        if float_compare(new_resolved, self.difference_qty, precision_rounding=rounding) >= 0:
            vals["state"] = "settled"
        self.sudo().write(vals)
        if not skip_recompute and self.truck_location_id:
            self.truck_location_id._compute_has_open_discrepancy()

