# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_pledge_product = fields.Boolean(
        string='Is Pledge Product',
        default=False,
        help='Check this if the product requires a pledge/deposit'
    )
    
    pledge_amount = fields.Monetary(
        string='Pledge Amount',
        currency_field='currency_id',
        help='Fixed pledge amount for this product (only used if Is Pledge Product = True)'
    )
    
    is_employee_service = fields.Boolean(
        string='Is Employee Service',
        default=False,
        help='Check this if the product represents an employee service'
    )
    
    is_delivery_product = fields.Boolean(
        string='Is Delivery Product',
        default=False,
        help='Check this if the product represents a delivery service'
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_pledge_product = fields.Boolean(
        related='product_tmpl_id.is_pledge_product', 
        store=True,
        readonly=False
    )
    pledge_amount = fields.Monetary(
        related='product_tmpl_id.pledge_amount', 
        store=True,
        readonly=False
    )
    is_employee_service = fields.Boolean(
        related='product_tmpl_id.is_employee_service',
        store=True,
        readonly=False
    )
    is_delivery_product = fields.Boolean(
        related='product_tmpl_id.is_delivery_product',
        store=True,
        readonly=False
    )
