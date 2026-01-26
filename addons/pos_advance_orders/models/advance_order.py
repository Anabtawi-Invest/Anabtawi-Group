from odoo import models, fields

class PosAdvanceOrder(models.Model):
    _name = "pos.advance.order"
    _description = "POS Advance Order"

    name = fields.Char(default="Advance Order")
    pos_config_id = fields.Many2one("pos.config", required=True)
    partner_id = fields.Many2one("res.partner")
    partner_mobile = fields.Char()
    due_date = fields.Date()
    note = fields.Text()

    line_ids = fields.One2many("pos.advance.order.line", "order_id")

    state = fields.Selection([
        ("draft", "Draft"),
        ("paid", "Paid"),
        ("fulfilled", "Fulfilled")
    ], default="draft")


class PosAdvanceOrderLine(models.Model):
    _name = "pos.advance.order.line"

    order_id = fields.Many2one("pos.advance.order")
    product_id = fields.Many2one("product.product")
    qty = fields.Float(default=1)
    price_unit = fields.Float()
    name = fields.Char()

