# -*- coding: utf-8 -*-

from odoo import api, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def get_receipt_template_for_pos_frontend(self):
        templates = super().get_receipt_template_for_pos_frontend()
        name = "pos_order_kitchen_ticket.pos_order_kitchen_ticket"
        templates.append([name, self.env["ir.qweb"]._get_template(name)[1]])
        return templates
