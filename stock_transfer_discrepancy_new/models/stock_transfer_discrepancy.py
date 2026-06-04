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

    # New flow:
    # - under_investigation: created at picking validation time, truck is still allowed
    # - open: investigation window expired, truck will be blocked by existing logic
    # - settled: fully resolved
    state = fields.Selection(
        [
            ("under_investigation", "Under Investigation"),
            ("open", "Open"),
            ("settled", "Settled"),
        ],
        string="State",
        default="under_investigation",
        required=True,
        index=True,
    )

    # Set at picking validation time (wizard confirm) and used for 48-hour grace window.
    validated_at = fields.Datetime(string="Validated At", index=True)
    investigation_deadline = fields.Datetime(string="Investigation Deadline", index=True)

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
    def _cron_expire_investigations(self):
        """Move discrepancies from under_investigation to open after deadline.

        We intentionally keep the existing 'truck blocking' logic unchanged:
        stock.location.has_open_discrepancy checks only state='open'.
        So, once a discrepancy becomes 'open', the truck will be blocked as before.
        """
        now = fields.Datetime.now()
        recs = self.search(
            [
                ("state", "=", "under_investigation"),
                ("investigation_deadline", "!=", False),
                ("investigation_deadline", "<=", now),
            ]
        )
        # Only escalate to OPEN if still not fully resolved.
        to_open = recs.filtered(lambda r: (r.difference_qty or 0.0) > (r.resolved_qty or 0.0))
        if not to_open:
            return

        to_open.write({"state": "open"})
        # Ensure the computed flag is updated for selection domain / constraints
        to_open.mapped("truck_location_id")._compute_has_open_discrepancy()

    @api.model
    def apply_resolution(
        self,
        truck_location,
        product,
        qty_in_product_uom,
        stage=None,
        exclude_picking_ids=None,
    ):
        """Apply a settlement quantity on (open/under_investigation) discrepancies for a truck/product.

        - qty_in_product_uom: quantity expressed in product default UoM.
        - stage: optional ('dispatch'/'receipt') to resolve only that stage.
        - exclude_picking_ids: optional list of pickings to exclude (e.g. current picking being processed).
        """
        if not truck_location or not product:
            return
        if not qty_in_product_uom:
            return

        domain = [
            ("truck_location_id", "=", truck_location.id),
            ("product_id", "=", product.id),
            ("state", "in", ("open", "under_investigation")),
        ]
        if stage:
            domain.append(("stage", "=", stage))
        if exclude_picking_ids:
            domain.append(("picking_id", "not in", exclude_picking_ids))

        # Oldest first
        discrepancies = self.sudo().search(domain, order="date asc, id asc")
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
        if self.state == "settled":
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

    def action_create_scrap(self):
        """Open a new scrap form prefilled from the discrepancy."""
        self.ensure_one()
        rounding = self.product_id.uom_id.rounding
        remaining_qty = max((self.difference_qty or 0.0) - (self.resolved_qty or 0.0), 0.0)
        if float_compare(remaining_qty, 0.0, precision_rounding=rounding) <= 0:
            remaining_qty = 0.0

        return {
            "type": "ir.actions.act_window",
            "name": "Scrap Order",
            "res_model": "stock.scrap",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_product_id": self.product_id.id,
                "default_product_uom_id": self.product_id.uom_id.id,
                "default_scrap_qty": remaining_qty,
                "default_location_id": self.truck_location_id.id,
                "default_company_id": self.company_id.id,
                "default_picking_id": self.picking_id.id,
                "default_origin": self.picking_id.name
                or self.picking_id.origin
                or self.display_name,
            },
        }
