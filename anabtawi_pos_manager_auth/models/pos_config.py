# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    require_manager_for_refund = fields.Boolean(
        string="Require Manager Barcode/PIN for Refunds",
        default=True,
        help="Enforce Manager authorization before performing order refunds."
    )
    require_manager_for_cancel = fields.Boolean(
        string="Require Manager Barcode/PIN for Order Cancellation",
        default=True,
        help="Enforce Manager authorization before canceling or deleting an open order."
    )
    require_manager_for_discount = fields.Boolean(
        string="Require Manager Barcode/PIN for Price & Discount",
        default=True,
        help="Enforce Manager authorization before applying manual price changes or custom discounts."
    )
    require_manager_for_cash_move = fields.Boolean(
        string="Require Manager Barcode/PIN for Cash In/Out",
        default=True,
        help="Enforce Manager authorization before executing Cash In or Cash Out moves."
    )

    def _loader_params_pos_config(self):
        result = super()._loader_params_pos_config()
        fields_to_add = [
            'require_manager_for_refund',
            'require_manager_for_cancel',
            'require_manager_for_discount',
            'require_manager_for_cash_move',
        ]
        search_fields = result.get('search_params', {}).get('fields', [])
        for f in fields_to_add:
            if f not in search_fields:
                search_fields.append(f)
        return result
