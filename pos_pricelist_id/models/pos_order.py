# -*- coding: utf-8 -*-
from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    customer_id_number = fields.Char(string="Customer ID Number")
