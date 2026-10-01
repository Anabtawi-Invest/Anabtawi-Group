from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    delivery_group_id = fields.Many2one(
        "sale.delivery.group",
        string="Delivery Group",
        index="btree_not_null",
        readonly=True,
    )
