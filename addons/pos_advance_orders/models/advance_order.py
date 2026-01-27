from odoo import models, fields, api


class PosAdvanceOrder(models.Model):
    _name = "pos.advance.order"
    _description = "POS Advance Order"

    name = fields.Char(default="Advance Order", required=True)

    pos_config_id = fields.Many2one(
        "pos.config",
        required=True
    )

    partner_id = fields.Many2one("res.partner")
    partner_mobile = fields.Char()
    due_date = fields.Date()
    note = fields.Text()

    line_ids = fields.One2many(
        "pos.advance.order.line",
        "order_id",
        string="Order Lines"
    )

    payment_ids = fields.One2many(
        "pos.advance.payment",
        "order_id",
        string="Payments"
    )

    invoice_id = fields.Many2one(
        "account.move",
        readonly=True
    )

    currency_id = fields.Many2one(
        "res.currency",
        related="pos_config_id.currency_id",
        store=True,
        readonly=True
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

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("fulfilled", "Fulfilled"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True
    )

    @api.depends("line_ids.price_subtotal", "payment_ids.amount")
    def _compute_amounts(self):
        for order in self:
            order.amount_total = sum(order.line_ids.mapped("price_subtotal"))
            order.amount_paid = sum(order.payment_ids.mapped("amount"))
            order.amount_due = order.amount_total - order.amount_paid


class PosAdvanceOrderLine(models.Model):
    _name = "pos.advance.order.line"
    _description = "POS Advance Order Line"

    order_id = fields.Many2one(
        "pos.advance.order",
        required=True,
        ondelete="cascade"
    )

    product_id = fields.Many2one(
        "product.product",
        required=True
    )

    name = fields.Char()
    qty = fields.Float(default=1.0)
    price_unit = fields.Float()

    currency_id = fields.Many2one(
        "res.currency",
        related="order_id.currency_id",
        store=True,
        readonly=True
    )

    price_subtotal = fields.Monetary(
        compute="_compute_price_subtotal",
        store=True
    )

    @api.depends("qty", "price_unit")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
