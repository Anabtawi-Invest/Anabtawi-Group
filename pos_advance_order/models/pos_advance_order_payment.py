# -*- coding: utf-8 -*-

from odoo import fields, models


class PosAdvanceOrderPayment(models.Model):
    _name = "pos.advance.order.payment"
    _description = "Advance Order Payment Split"
    _order = "id"

    order_id = fields.Many2one(
        "pos.advance.order",
        string="Advance Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="Payment Method",
        required=True,
        ondelete="restrict",
    )
    amount = fields.Monetary(string="Amount", required=True, currency_field="currency_id")
    payment_stage = fields.Selection(
        [
            ("deposit", "Deposit"),
            ("completion", "Completion"),
        ],
        string="Stage",
        required=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="order_id.currency_id",
        store=True,
        readonly=True,
    )
