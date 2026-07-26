# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CakeCategory(models.Model):
    _name = "cake.category"
    _description = "Cake Category"
    _order = "sequence, id"

    name_ar = fields.Char(string="Category Name (Arabic)", required=True)
    name_en = fields.Char(string="Category Name (English)", required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    line_ids = fields.One2many("cake.category.line", "category_id", string="Products")

    def name_get(self):
        result = []
        for record in self:
            lang = self.env.lang or "en_US"
            if lang.startswith("ar"):
                name = record.name_ar or record.name_en
            else:
                name = record.name_en or record.name_ar
            result.append((record.id, name))
        return result


class CakeCategoryLine(models.Model):
    _name = "cake.category.line"
    _description = "Cake Category Line"
    _order = "sequence, id"

    category_id = fields.Many2one("cake.category", string="Category", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product", required=True)
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    cost = fields.Float(string="Cost", required=True, digits="Product Price")
    total_cost = fields.Float(
        string="Total Cost",
        compute="_compute_total_cost",
        store=True,
        digits="Product Price",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.depends("quantity", "cost")
    def _compute_total_cost(self):
        for line in self:
            line.total_cost = line.quantity * line.cost

    @api.constrains("quantity", "cost")
    def _check_positive_values(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))
            if line.cost < 0:
                raise ValidationError(_("Cost cannot be negative."))
