from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    delivery_split_location_ids = fields.Many2many(
        "stock.location",
        "res_company_delivery_split_location_rel",
        "company_id",
        "location_id",
        string="Split Delivery Customer Locations",
    )
