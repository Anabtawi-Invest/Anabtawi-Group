# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CakeCategory(models.Model):
    _name = "cake.category"
    _description = "Cake Category"
    _order = "sequence, id"

    name = fields.Char(string="Category Name", required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    line_ids = fields.One2many("cake.category.line", "category_id", string="Products")


class CakeCategoryLine(models.Model):
    _name = "cake.category.line"
    _description = "Cake Category Line"
    _order = "sequence, id"

    category_id = fields.Many2one("cake.category", string="Category", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product", required=True)
    cost = fields.Float(string="Cost", required=True, digits="Product Price")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains("cost")
    def _check_positive_values(self):
        for line in self:
            if line.cost < 0:
                raise ValidationError(_("Cost cannot be negative."))
