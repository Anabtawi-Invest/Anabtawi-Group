# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_self_ordering_url = fields.Char(
        string='Self-Order URL',
        related='pos_config_id.self_ordering_url',
        readonly=True,
    )
    pos_self_order_payment_choice_enabled = fields.Boolean(
        related='pos_config_id.self_order_payment_choice_enabled',
        readonly=False,
    )
    pos_self_order_allow_cash_on_delivery = fields.Boolean(
        related='pos_config_id.self_order_allow_cash_on_delivery',
        readonly=False,
    )
    pos_self_order_allow_online_card = fields.Boolean(
        related='pos_config_id.self_order_allow_online_card',
        readonly=False,
    )
    pos_self_order_require_customer_phone = fields.Boolean(
        related='pos_config_id.self_order_require_customer_phone',
        readonly=False,
    )
    pos_self_order_require_phone_otp = fields.Boolean(
        related='pos_config_id.self_order_require_phone_otp',
        readonly=False,
    )
    pos_self_order_otp_show_debug_code = fields.Boolean(
        related='pos_config_id.self_order_otp_show_debug_code',
        readonly=False,
    )
