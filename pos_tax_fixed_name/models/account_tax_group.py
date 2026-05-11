from odoo import api, fields, models


class AccountTaxGroup(models.Model):
    _inherit = "account.tax.group"

    pos_fixed_group_name = fields.Char(
        string="POS Fixed Tax Line Name",
        translate=False,
        help="If set, POS tax summary uses this name instead of Tax Group name.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "pos_fixed_group_name" not in fields_to_load:
            fields_to_load.append("pos_fixed_group_name")
        return fields_to_load
