# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pledge_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_pledge_currency_id",
        readonly=True,
    )
    pledge_amount = fields.Monetary(
        string="Pledge Amount",
        currency_field="pledge_currency_id",
        default=0.0,
        help="Deposit amount when this product is used as a Site Service pledge product.",
    )
    # Kept so leftover/old product form views still load. Pledge is driven by
    # Site Service menu mapping, not this flag.
    has_pledge = fields.Boolean(
        string="Has Pledge",
        default=False,
        help="Deprecated. Pledge products are mapped on the Site Service menu, not this checkbox.",
    )

    is_employee_service = fields.Boolean(
        string="Is Employee Service",
        default=False,
        help="Check this if the product represents an employee service",
    )
    is_delivery_product = fields.Boolean(
        string="Is Delivery Product",
        default=False,
        help="Check this if the product represents a delivery service",
    )

    @api.depends("company_id")
    def _compute_pledge_currency_id(self):
        for rec in self:
            rec.pledge_currency_id = (rec.company_id or self.env.company).currency_id


class ProductProduct(models.Model):
    _inherit = "product.product"

    pledge_amount = fields.Monetary(related="product_tmpl_id.pledge_amount", store=True, readonly=False)
    pledge_currency_id = fields.Many2one(related="product_tmpl_id.pledge_currency_id", store=True, readonly=True)
    has_pledge = fields.Boolean(related="product_tmpl_id.has_pledge", store=True, readonly=False)
    is_employee_service = fields.Boolean(related="product_tmpl_id.is_employee_service", store=True, readonly=False)
    is_delivery_product = fields.Boolean(related="product_tmpl_id.is_delivery_product", store=True, readonly=False)
