from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    factory_plan_category = fields.Char(
        string="Factory Plan Category",
        translate=True,
    )
