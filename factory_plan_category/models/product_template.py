from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    factory_plan_category = fields.Char(
        string="Factory Plan Category",
        translate=True,
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    factory_plan_category = fields.Char(
        related="product_tmpl_id.factory_plan_category",
        store=True,
        readonly=True,
        index=True,
    )
