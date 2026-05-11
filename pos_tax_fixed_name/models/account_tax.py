from odoo import api, fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    pos_fixed_name = fields.Char(
        string="POS Fixed Display Name",
        translate=False,
        help="If set, POS uses this value instead of translated tax names.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "pos_fixed_name" not in fields_to_load:
            fields_to_load.append("pos_fixed_name")
        return fields_to_load
