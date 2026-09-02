# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BranchSupplyFlowSnapshotLine(models.Model):
    _name = "branch.supply.flow.snapshot.line"
    _description = "Branch Supply Flow Snapshot Line"
    _order = "snapshot_id desc, location_id, product_id"

    snapshot_id = fields.Many2one(
        "branch.supply.flow.snapshot",
        string="Snapshot",
        required=True,
        ondelete="cascade",
        index=True,
    )
    snapshot_date = fields.Datetime(
        related="snapshot_id.snapshot_date",
        string="Generated On",
        store=True,
        readonly=True,
    )
    date_from = fields.Datetime(
        related="snapshot_id.date_from",
        string="Period From",
        store=True,
        readonly=True,
    )
    date_to = fields.Datetime(
        related="snapshot_id.date_to",
        string="Period To",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="snapshot_id.company_id",
        string="Company",
        store=True,
        readonly=True,
    )
    location_id = fields.Many2one("stock.location", string="Branch Location", readonly=True, index=True)
    location_name = fields.Char(
        related="location_id.complete_name",
        string="Branch Location",
        readonly=True,
    )
    product_id = fields.Many2one("product.product", string="Product", readonly=True, index=True)
    product_categ_id = fields.Many2one(
        related="product_id.categ_id",
        string="Product Category",
        store=True,
        readonly=True,
    )
    uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="Unit of Measure",
        readonly=True,
    )

    requested_qty = fields.Float(string="Requested Qty", digits="Product Unit", readonly=True)
    sent_qty = fields.Float(string="Sent Qty (Net)", digits="Product Unit", readonly=True)
    sent_return_qty = fields.Float(string="Sent Returns", digits="Product Unit", readonly=True)
    received_qty = fields.Float(string="Received Qty (Net)", digits="Product Unit", readonly=True)
    received_return_qty = fields.Float(string="Received Returns", digits="Product Unit", readonly=True)
    sold_qty = fields.Float(string="Sold Qty (POS)", digits="Product Unit", readonly=True)

    variance_sent_received = fields.Float(
        string="Sent - Received",
        digits="Product Unit",
        readonly=True,
    )
    variance_received_sold = fields.Float(
        string="Received - Sold",
        digits="Product Unit",
        readonly=True,
    )

    fill_rate = fields.Float(
        string="Fill Rate %",
        digits=(16, 2),
        compute="_compute_kpis",
        store=True,
    )
    transit_loss_rate = fields.Float(
        string="Transit Loss %",
        digits=(16, 2),
        compute="_compute_kpis",
        store=True,
    )
    sell_through_rate = fields.Float(
        string="Sell-through %",
        digits=(16, 2),
        compute="_compute_kpis",
        store=True,
    )
    has_transit_loss = fields.Boolean(
        string="Transit Loss",
        compute="_compute_kpis",
        store=True,
    )
    has_low_sell_through = fields.Boolean(
        string="Low Sell-through",
        compute="_compute_kpis",
        store=True,
    )
    has_unsold_stock = fields.Boolean(
        string="Unsold Stock",
        compute="_compute_kpis",
        store=True,
    )
    has_issue = fields.Boolean(
        string="Has Issue",
        compute="_compute_kpis",
        store=True,
    )

    @api.depends(
        "requested_qty",
        "sent_qty",
        "received_qty",
        "sold_qty",
        "variance_sent_received",
        "variance_received_sold",
    )
    def _compute_kpis(self):
        transit_loss_threshold = 5.0
        sell_through_threshold = 50.0
        unsold_threshold = 0.01

        for line in self:
            line.fill_rate = (
                line.received_qty / line.requested_qty * 100.0
                if line.requested_qty else 0.0
            )
            line.transit_loss_rate = (
                line.variance_sent_received / line.sent_qty * 100.0
                if line.sent_qty else 0.0
            )
            line.sell_through_rate = (
                line.sold_qty / line.received_qty * 100.0
                if line.received_qty else 0.0
            )

            line.has_transit_loss = line.transit_loss_rate > transit_loss_threshold
            line.has_low_sell_through = (
                line.received_qty > 0.0 and line.sell_through_rate < sell_through_threshold
            )
            line.has_unsold_stock = line.variance_received_sold > unsold_threshold
            line.has_issue = (
                line.has_transit_loss or line.has_low_sell_through or line.has_unsold_stock
            )
