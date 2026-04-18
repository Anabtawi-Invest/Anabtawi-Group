from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    open_amount = fields.Monetary(
        copy=False,
        help="Informational Open Amount shown in the POS without affecting accounting entries.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if fields_to_load and "open_amount" not in fields_to_load:
            fields_to_load.append("open_amount")
        return fields_to_load
