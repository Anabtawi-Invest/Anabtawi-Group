import logging

from odoo import api, fields, models
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


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
    driver_id = fields.Many2one(
        "stock.transfer.driver",
        string="Driver",
        index=True,
        ondelete="set null",
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

    # Set at picking validation time (wizard confirm); length of grace window is set in the wizard (e.g. 1 min for tests, 48h prod).
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
    destination_location_id = fields.Many2one(
        "stock.location",
        string="Destination Location",
        related="picking_id.location_dest_id",
        store=True,
        readonly=True,
    )

    @api.depends("expected_qty", "actual_qty")
    def _compute_difference_qty(self):
        for rec in self:
            rec.difference_qty = (rec.expected_qty or 0.0) - (rec.actual_qty or 0.0)

    @api.model
    def _cron_expire_investigations(self):
        """Move discrepancies from under_investigation to open after deadline.

        Once a discrepancy becomes 'open', stock.transfer.driver.is_blocked is updated;
        stock.location.has_open_discrepancy is still recomputed for reporting.
        """
        now = fields.Datetime.now()
        _logger.info(
            "[DISCREPANCY_CRON] _cron_expire_investigations started, server_now=%s",
            now,
        )
        recs = self.search(
            [
                ("state", "=", "under_investigation"),
                ("investigation_deadline", "!=", False),
                ("investigation_deadline", "<=", now),
            ]
        )
        _logger.info(
            "[DISCREPANCY_CRON] candidates (under_investigation, deadline passed): count=%s ids=%s",
            len(recs),
            recs.ids,
        )
        for r in recs:
            _logger.info(
                "[DISCREPANCY_CRON]   id=%s picking=%s driver_id=%s driver=%s deadline=%s "
                "diff_qty=%s resolved_qty=%s state=%s",
                r.id,
                r.picking_id.display_name,
                r.driver_id.id if r.driver_id else None,
                r.driver_id.display_name if r.driver_id else None,
                r.investigation_deadline,
                r.difference_qty,
                r.resolved_qty,
                r.state,
            )

        # Only escalate to OPEN if still not fully resolved.
        to_open = recs.filtered(
            lambda r: float_compare(
                (r.difference_qty or 0.0),
                (r.resolved_qty or 0.0),
                precision_rounding=r.product_id.uom_id.rounding,
            )
            > 0
        )
        skipped_resolved = recs - to_open
        if skipped_resolved:
            _logger.info(
                "[DISCREPANCY_CRON] skipped (already fully resolved vs difference): ids=%s",
                skipped_resolved.ids,
            )

        if not to_open:
            if not recs:
                all_ui = self.search([("state", "=", "under_investigation")])
                still_future = all_ui.filtered(
                    lambda r: r.investigation_deadline and r.investigation_deadline > now
                )
                no_deadline = all_ui.filtered(lambda r: not r.investigation_deadline)
                for r in still_future:
                    _logger.warning(
                        "[DISCREPANCY_CRON] NOT escalating id=%s: investigation_deadline=%s is AFTER "
                        "server_now=%s (wait until deadline in UTC, or shorten deadline for testing). "
                        "picking=%s driver_id=%s",
                        r.id,
                        r.investigation_deadline,
                        now,
                        r.picking_id.display_name,
                        r.driver_id.id if r.driver_id else None,
                    )
                _logger.warning(
                    "[DISCREPANCY_CRON] nothing to escalate: no under_investigation row has "
                    "investigation_deadline <= server_now. counts: all_under_investigation=%s "
                    "still_future_deadline=%s missing_deadline=%s server_now=%s",
                    len(all_ui),
                    len(still_future),
                    len(no_deadline),
                    now,
                )
            else:
                _logger.info(
                    "[DISCREPANCY_CRON] deadline passed for ids=%s but none escalated: "
                    "all already fully resolved (difference_qty <= resolved_qty)",
                    recs.ids,
                )
            return

        _logger.info(
            "[DISCREPANCY_CRON] escalating to state=open: ids=%s",
            to_open.ids,
        )
        to_open.write({"state": "open"})
        to_open.mapped("truck_location_id")._compute_has_open_discrepancy()
        drivers = to_open.mapped("driver_id").filtered(lambda d: d)
        missing_driver = to_open.filtered(lambda r: not r.driver_id)
        if missing_driver:
            _logger.warning(
                "[DISCREPANCY_CRON] escalated rows have NO driver_id — is_blocked will NOT update "
                "for any driver. discrepancy_ids=%s pickings=%s",
                missing_driver.ids,
                missing_driver.mapped("picking_id.name"),
            )
        _logger.info(
            "[DISCREPANCY_CRON] drivers to recompute is_blocked: ids=%s names=%s",
            drivers.ids,
            drivers.mapped("display_name"),
        )
        if drivers:
            drivers._compute_is_blocked()
        else:
            _logger.warning(
                "[DISCREPANCY_CRON] no driver records on escalated discrepancies; "
                "_compute_is_blocked not called",
            )

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
            drivers = discrepancies.mapped("driver_id").filtered(lambda d: d)
            if drivers:
                drivers._compute_is_blocked()

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
            if not skip_recompute:
                if self.truck_location_id:
                    self.truck_location_id._compute_has_open_discrepancy()
                if self.driver_id:
                    self.driver_id._compute_is_blocked()
            return

        to_apply = min(qty_in_product_uom, remaining)
        if float_compare(to_apply, 0.0, precision_rounding=rounding) <= 0:
            return

        new_resolved = (self.resolved_qty or 0.0) + to_apply
        vals = {"resolved_qty": new_resolved}
        if float_compare(new_resolved, self.difference_qty, precision_rounding=rounding) >= 0:
            vals["state"] = "settled"

        self.sudo().write(vals)
        if not skip_recompute:
            if self.truck_location_id:
                self.truck_location_id._compute_has_open_discrepancy()
            if self.driver_id:
                self.driver_id._compute_is_blocked()
