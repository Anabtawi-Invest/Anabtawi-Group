from odoo import models, fields, api

class PosAdvanceOrder(models.Model):
    _name = "pos.advance.order"
    _description = "POS Advance Order"

    name = fields.Char(default="New")
    state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("fulfilled", "Fulfilled"),
        ("cancelled", "Cancelled"),
    ], default="draft")

    pos_config_id = fields.Many2one("pos.config")
    partner_id = fields.Many2one("res.partner")
    partner_mobile = fields.Char()
    due_date = fields.Date()
    invoice_id = fields.Many2one("account.move")
    note = fields.Text()

    currency_id = fields.Many2one(
        "res.currency",
        related="pos_config_id.currency_id",
        store=True
    )

    line_ids = fields.One2many(
        "pos.advance.order.line",
        "order_id"
    )

    payment_ids = fields.One2many(
        "pos.advance.payment",
        "order_id"
    )

    amount_total = fields.Monetary(
        compute="_compute_amounts",
        store=True
    )
    amount_paid = fields.Monetary(
        compute="_compute_amounts",
        store=True
    )
    amount_due = fields.Monetary(
        compute="_compute_amounts",
        store=True
    )

    @api.depends("line_ids.price_subtotal", "payment_ids.amount")
    def _compute_amounts(self):
        for order in self:
            total = sum(order.line_ids.mapped("price_subtotal"))
            paid = sum(order.payment_ids.mapped("amount"))
            order.amount_total = total
            order.amount_paid = paid
            order.amount_due = total - paid
