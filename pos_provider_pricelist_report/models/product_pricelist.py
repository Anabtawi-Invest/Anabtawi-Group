from odoo import api, fields, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    is_provider = fields.Boolean(string="Is Provider")

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "is_provider" not in fields_to_load:
            fields_to_load.append("is_provider")
        return fields_to_load
