# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosAdvanceOrderPledge(models.Model):
    _name = "pos.advance.order.pledge"
    _description = "POS Advance Order Pledge"
    _order = "id desc"

    order_id = fields.Many2one("pos.advance.order", required=True, ondelete="cascade")
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain=[("available_in_pos", "=", True)],
    )
    pledge_qty = fields.Float(string="Pledge Qty", default=1.0)
    pledge_amount_unit = fields.Monetary(
        string="Pledge Unit Amount",
        currency_field="currency_id",
        default=0.0,
    )
    currency_id = fields.Many2one(related="order_id.currency_id", store=True, readonly=True)
    pledge_subtotal = fields.Monetary(
        string="Pledge Total",
        currency_field="currency_id",
        compute="_compute_pledge_subtotal",
        store=True,
        readonly=True,
    )

    @api.depends("pledge_qty", "pledge_amount_unit")
    def _compute_pledge_subtotal(self):
        for rec in self:
            rec.pledge_subtotal = (rec.pledge_qty or 0.0) * (rec.pledge_amount_unit or 0.0)

