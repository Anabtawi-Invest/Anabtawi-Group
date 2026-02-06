# -*- coding: utf-8 -*-
from odoo import api, fields, models

class BranchSupplyLine(models.Model):
    _name = "branch.supply.line"
    _description = "Branch Supply Line"

    order_id = fields.Many2one("branch.supply.order", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", required=True, index=True)
    product_uom_id = fields.Many2one("uom.uom", string="UoM", related="product_id.uom_id", store=True, readonly=True)

    requested_qty = fields.Float(required=True, default=0.0)
    loaded_qty = fields.Float(default=0.0)
    received_qty = fields.Float(default=0.0)

    available_qty = fields.Float(readonly=True, help="Available qty at source warehouse stock location at approval time.")
    shortage_qty = fields.Float(readonly=True, help="Missing qty that triggered manufacturing/procurement.")
    mo_id = fields.Many2one("mrp.production", string="Manufacturing Order", readonly=True, copy=False)
    po_id = fields.Many2one("purchase.order", string="Purchase Order", readonly=True, copy=False)

    warehouse_gap_qty = fields.Float(compute="_compute_gaps", store=True, readonly=True)
    transit_gap_qty = fields.Float(compute="_compute_gaps", store=True, readonly=True)

    @api.depends("requested_qty", "loaded_qty", "received_qty")
    def _compute_gaps(self):
        for line in self:
            rq = line.requested_qty or 0.0
            lq = line.loaded_qty or 0.0
            rcq = line.received_qty or 0.0
            line.warehouse_gap_qty = max(rq - lq, 0.0)
            line.transit_gap_qty = max(lq - rcq, 0.0)
