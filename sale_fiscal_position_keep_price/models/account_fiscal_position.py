from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _inherit = "account.fiscal.position"

    keep_pricelist_price_after_tax_mapping = fields.Boolean(
        string="Keep Pricelist Price on Tax Mapping",
        help=(
            "When enabled, sales unit price keeps the original pricelist value and "
            "is not recalculated when taxes are remapped by this fiscal position."
        ),
    )

    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "keep_pricelist_price_after_tax_mapping" not in fields_to_load:
            fields_to_load.append("keep_pricelist_price_after_tax_mapping")
        return fields_to_load
