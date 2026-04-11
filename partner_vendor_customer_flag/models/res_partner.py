from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"

    x_is_vendor = fields.Boolean(string="Is Vendor")
    x_is_customer = fields.Boolean(string="Is Customer")
