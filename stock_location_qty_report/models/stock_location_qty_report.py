# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLocationQtyReportLine(models.TransientModel):
    _name = "stock.location.qty.report.line"
    _description = "Stock Location Quantity Report Line"
    _order = "location_id, product_id"

    wizard_id = fields.Many2one(
        "stock.location.qty.wizard",
        string="Wizard",
        ondelete="cascade",
    )
    qty_mode = fields.Selection(
        [
            ("planned", "Planned (Not Done)"),
            ("done", "Done"),
        ],
        string="Incoming / Outgoing Mode",
        readonly=True,
    )
    location_id = fields.Many2one("stock.location", string="Location", readonly=True)
    location_name = fields.Char(
        related="location_id.complete_name",
        string="Location",
        readonly=True,
    )
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    default_code = fields.Char(
        related="product_id.default_code",
        string="Internal Reference",
        readonly=True,
    )
    uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="Unit of Measure",
        readonly=True,
    )
    uom_name = fields.Char(
        related="product_id.uom_id.display_name",
        string="Unit of Measure",
        readonly=True,
    )

    qty_on_hand = fields.Float(string="On Hand", digits="Product Unit", readonly=True)
    qty_incoming = fields.Float(string="Incoming", digits="Product Unit", readonly=True)
    qty_outgoing = fields.Float(string="Outgoing", digits="Product Unit", readonly=True)
    qty_forecast = fields.Float(
        string="Forecast",
        digits="Product Unit",
        readonly=True,
        help="On Hand + Incoming - Outgoing (meaningful for Planned mode).",
    )
