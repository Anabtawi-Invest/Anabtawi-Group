# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    enable_fulfillment_schedule = fields.Boolean(
        string="Enable Fulfillment Scheduling (طلبيات تواصي)",
        default=True,
        help="Enables store pickup and home delivery scheduling with field validations in POS.",
    )
    advance_deposit_account_id = fields.Many2one(
        "account.account",
        string="Customer Advance Deposit Account (حساب عربون العملاء)",
        domain="[('account_type', '=', 'liability_current')]",
        default=lambda self: self.env.ref("pos_scheduled_orders.account_customer_advance_deposits", raise_if_not_found=False),
        help="Balance sheet current liability account used to hold initial partial deposits on scheduled orders.",
    )
    delivery_fee_product_id = fields.Many2one(
        "product.product",
        string="Default Delivery Fee Product (منتج رسوم التوصيل)",
        domain="[('type', '=', 'service')]",
        default=lambda self: self.env.ref("pos_scheduled_orders.product_product_delivery_fee", raise_if_not_found=False),
        help="Service product automatically added when cashiers enter a delivery fee.",
    )
    catering_fee_product_id = fields.Many2one(
        "product.product",
        string="Default Catering Fee Product (منتج رسوم الضيافة)",
        domain="[('type', '=', 'service')]",
        default=lambda self: self.env.ref("pos_scheduled_orders.product_product_catering_fee", raise_if_not_found=False),
        help="Service product automatically added when cashiers add a catering fee.",
    )
    allowed_fulfillment_branch_ids = fields.Many2many(
        "pos.config",
        "pos_config_fulfillment_branch_rel",
        "config_id",
        "branch_id",
        string="Allowed Fulfillment Branches (فروع التواصي المسموحة)",
        help="Allowed POS branch locations for cross-branch pickup and fulfillment.",
    )
