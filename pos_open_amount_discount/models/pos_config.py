from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    maximum_open_amount = fields.Float(
        string="Maximum Open Amount",
        default=0.0,
        help=(
            "Maximum fixed amount cashiers can deduct from the order total using "
            "the Open Amount button. Set to 0 to disable the feature."
        ),
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        if "maximum_open_amount" not in fields_to_load:
            fields_to_load.append("maximum_open_amount")
        return fields_to_load
