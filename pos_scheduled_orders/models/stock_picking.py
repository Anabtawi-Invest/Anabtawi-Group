# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    fulfillment_type = fields.Selection(
        selection=[
            ("pickup", "Store Pickup - استلام من الفرع"),
            ("delivery", "Home Delivery - توصيل منزلي"),
        ],
        string="Fulfillment Type (نوع الطلب)",
        copy=False,
    )
    pickup_delivery_datetime = fields.Datetime(
        string="Scheduled Date & Time (موعد التسليم)",
        copy=False,
    )
    delivery_address_id = fields.Many2one(
        "res.partner",
        string="Delivery Address (عنوان التوصيل)",
        copy=False,
    )
    is_catering = fields.Boolean(
        string="Is Catering (طلب ضيافة كترنج)",
        default=False,
        copy=False,
    )

    def action_validate_fulfillment_picking(self):
        """
        Validates the stock picking upon final customer handover on Day 2.
        """
        for picking in self:
            if picking.state not in ["done", "cancel"]:
                picking.action_assign()
                if picking.state == "assigned":
                    picking.button_validate()
        return True
