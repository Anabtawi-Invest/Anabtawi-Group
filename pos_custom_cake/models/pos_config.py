# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    enable_custom_cake = fields.Boolean(string="Enable Custom Cake")
