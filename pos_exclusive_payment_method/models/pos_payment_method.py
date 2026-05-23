from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    exclusive_payment_method = fields.Boolean(
        string="Exclusive Payment Method",
        help="If enabled, this payment method cannot be combined with any other payment method in the same POS order.",
    )

    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if "exclusive_payment_method" not in fields_list:
            fields_list.append("exclusive_payment_method")
        return fields_list
