# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = 'pos.config'

    self_order_payment_choice_enabled = fields.Boolean(
        string='Let Customer Choose Payment Method',
        default=True,
        help='Show pay-by-card vs cash-on-delivery choice on the mobile self-order cart.',
    )
    self_order_allow_cash_on_delivery = fields.Boolean(
        string='Allow Cash on Delivery',
        default=True,
    )
    self_order_allow_online_card = fields.Boolean(
        string='Allow Pay by Card Online',
        default=True,
    )
    self_order_require_customer_phone = fields.Boolean(
        string='Require Customer Phone',
        default=True,
        help='Customers must verify their phone number before placing a mobile self-order.',
    )
    self_order_require_phone_otp = fields.Boolean(
        string='Require Phone OTP Verification',
        default=False,
        help='When enabled, customers must enter a one-time code sent to their phone. Requires SMS integration.',
    )
    self_order_otp_show_debug_code = fields.Boolean(
        string='Show OTP Code in Response (Debug)',
        default=False,
        help='Return the OTP code in the API response for testing until SMS is configured.',
    )

    @api.constrains(
        'self_order_allow_cash_on_delivery',
        'self_order_allow_online_card',
        'self_order_payment_choice_enabled',
    )
    def _check_payment_choice_options(self):
        for config in self:
            if not config.self_order_payment_choice_enabled:
                continue
            if not config.self_order_allow_cash_on_delivery and not config.self_order_allow_online_card:
                raise ValidationError(_('Enable at least one self-order payment option.'))

    @api.model
    def _load_pos_self_data_fields(self, config):
        fields_list = super()._load_pos_self_data_fields(config)
        # Empty list means "load all fields" for self-order; do not narrow it.
        if not fields_list:
            return fields_list
        for field_name in (
            'self_order_payment_choice_enabled',
            'self_order_allow_cash_on_delivery',
            'self_order_allow_online_card',
            'self_order_require_customer_phone',
            'self_order_require_phone_otp',
            'self_order_otp_show_debug_code',
        ):
            if field_name not in fields_list:
                fields_list.append(field_name)
        return fields_list
