# -*- coding: utf-8 -*-
from odoo import fields, models


class BranchSupplyFlowReportLine(models.TransientModel):
    _name = "branch.supply.flow.report.line"
    _description = "Branch Supply Flow Report Line"
    _order = "location_id, product_id"

    wizard_id = fields.Many2one(
        "branch.supply.flow.wizard",
        string="Wizard",
        ondelete="cascade",
    )
    location_id = fields.Many2one("stock.location", string="Branch Location", readonly=True)
    location_name = fields.Char(
        related="location_id.complete_name",
        string="Branch Location",
        readonly=True,
    )
    product_id = fields.Many2one("product.product", string="Product", readonly=True)

    requested_qty = fields.Float(string="Requested Qty", digits="Product Unit", readonly=True)
    sent_qty = fields.Float(string="Sent Qty (Net)", digits="Product Unit", readonly=True)
    received_qty = fields.Float(string="Received Qty (Net)", digits="Product Unit", readonly=True)
    return_qty = fields.Float(
        string="Returns",
        digits="Product Unit",
        readonly=True,
        help="Total returns from dispatch and receipt transfers.",
    )
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
