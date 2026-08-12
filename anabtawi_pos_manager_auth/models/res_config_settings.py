# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_require_manager_for_refund = fields.Boolean(
        related='pos_config_id.require_manager_for_refund',
        readonly=False,
        string="Require Manager Barcode/PIN for Refunds"
    )
    pos_require_manager_for_cancel = fields.Boolean(
        related='pos_config_id.require_manager_for_cancel',
        readonly=False,
        string="Require Manager Barcode/PIN for Order Cancellation"
    )
    pos_require_manager_for_discount = fields.Boolean(
        related='pos_config_id.require_manager_for_discount',
        readonly=False,
        string="Require Manager Barcode/PIN for Price & Discount"
    )
    pos_require_manager_for_cash_move = fields.Boolean(
        related='pos_config_id.require_manager_for_cash_move',
        readonly=False,
        string="Require Manager Barcode/PIN for Cash In/Out"
    )
