# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPeriodMovementReportLine(models.TransientModel):
    _name = "stock.period.movement.report.line"
    _description = "Stock Period Movement Report Line"
    _order = "location_id, product_id"

    wizard_id = fields.Many2one(
        "stock.period.movement.wizard",
        string="Wizard",
        ondelete="cascade",
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

    qty_opening = fields.Float(string="Opening", digits="Product Unit", readonly=True)
    qty_receipt = fields.Float(string="Receipt", digits="Product Unit", readonly=True)
    qty_sale = fields.Float(string="Sale", digits="Product Unit", readonly=True)
    qty_transfer_in = fields.Float(string="Transfer In", digits="Product Unit", readonly=True)
    qty_transfer_out = fields.Float(string="Transfer Out", digits="Product Unit", readonly=True)
    qty_other_in = fields.Float(string="Other In", digits="Product Unit", readonly=True)
    qty_other_out = fields.Float(string="Other Out", digits="Product Unit", readonly=True)
    qty_closing = fields.Float(string="Closing", digits="Product Unit", readonly=True)
