# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Standard pledge fields (aligned with pos_advance_order)
    has_pledge = fields.Boolean(string="Has Pledge")
    pledge_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_pledge_currency_id",
        readonly=True,
    )
    pledge_amount = fields.Monetary(
        string="Pledge Amount",
        currency_field="pledge_currency_id",
        default=0.0,
        help="Fixed pledge amount for this product (only used if Has Pledge = True).",
    )

    # Backward-compatibility alias for existing pos_pledge code (JS/Python/XML)
    is_pledge_product = fields.Boolean(
        string="Is Pledge Product",
        related="has_pledge",
        store=True,
        readonly=False,
        help="Backward compatible alias of 'Has Pledge'.",
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

    def init(self):
        # Data migration: older versions used 'is_pledge_product'.
        # Copy TRUE values into the new canonical field 'has_pledge' (idempotent).
        self.env.cr.execute(
            """
            UPDATE product_template
               SET has_pledge = TRUE
             WHERE is_pledge_product = TRUE
               AND (has_pledge IS NULL OR has_pledge = FALSE)
            """
        )

    @api.depends("company_id")
    def _compute_pledge_currency_id(self):
        for rec in self:
            rec.pledge_currency_id = (rec.company_id or self.env.company).currency_id


class ProductProduct(models.Model):
    _inherit = "product.product"

    has_pledge = fields.Boolean(related="product_tmpl_id.has_pledge", store=True, readonly=False)
    pledge_amount = fields.Monetary(related="product_tmpl_id.pledge_amount", store=True, readonly=False)
    pledge_currency_id = fields.Many2one(related="product_tmpl_id.pledge_currency_id", store=True, readonly=True)

    # Backward compatibility for existing POS code
    is_pledge_product = fields.Boolean(related="product_tmpl_id.is_pledge_product", store=True, readonly=False)
    is_employee_service = fields.Boolean(related="product_tmpl_id.is_employee_service", store=True, readonly=False)
    is_delivery_product = fields.Boolean(related="product_tmpl_id.is_delivery_product", store=True, readonly=False)
