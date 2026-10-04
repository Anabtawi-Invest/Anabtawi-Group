# -*- coding: utf-8 -*-
from odoo import models, fields, api


class OnlineSalesChannel(models.Model):
    _name = "online.sales.channel"
    _description = "Online & Delivery Sales Channel"
    _order = "sequence, name"

    name = fields.Char(string="Channel Name", required=True)
    code = fields.Char(string="Channel Code", required=True, help="Unique code e.g. TALABAT, CAREEM, WEBSITE, MYTHINGS")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Char(string="HEX Color", default="#0083B0", help="Color badge used in dashboard charts and UI")
    commission_rate = fields.Float(string="Commission Rate (%)", help="Platform commission percentage deducted from gross sales", default=0.0)
    keywords = fields.Text(string="Matching Keywords", help="Comma-separated keywords to identify payment methods or order tags (e.g. talabat,طلبات)")
    
    payment_method_ids = fields.Many2many(
        "pos.payment.method",
        string="Linked POS Payment Methods",
        help="Explicit payment methods assigned to this online delivery channel"
    )

    @api.model
    def create_default_channels(self):
        """Seed default online & delivery channels if not already existing."""
        defaults = [
            {"name": "Talabat (طلبات)", "code": "TALABAT", "color": "#FF5722", "commission_rate": 18.0, "keywords": "talabat, طلبات"},
            {"name": "Careem (كريم)", "code": "CAREEM", "color": "#4CAF50", "commission_rate": 15.0, "keywords": "careem, كريم"},
            {"name": "MyThings / Ashyaty (أشياتي)", "code": "MYTHINGS", "color": "#9C27B0", "commission_rate": 12.0, "keywords": "mythings, ashyaty, أشياتي"},
            {"name": "Kabseh (كبسة)", "code": "KABSEH", "color": "#FF9800", "commission_rate": 15.0, "keywords": "kabseh, كبسة"},
            {"name": "Website / E-Commerce", "code": "WEBSITE", "color": "#2196F3", "commission_rate": 0.0, "keywords": "website, ecommerce, online_store, موقع"},
            {"name": "Direct Phone / App Delivery", "code": "DIRECT_DELIVERY", "color": "#00BCD4", "commission_rate": 0.0, "keywords": "delivery, توصيل, direct"},
        ]
        for d in defaults:
            if not self.sudo().search([("code", "=", d["code"])], limit=1):
                self.sudo().create(d)
