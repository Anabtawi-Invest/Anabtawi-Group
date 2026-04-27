from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # (باقي الحقول عندك كما هي)

    @api.model
    def _load_pos_data_fields(self, config):
        """
        Odoo 19: Ensure core POS fields are always loaded.
        Your POS crash happens when currency_id is missing in loaded config.
        """
        fields_to_load = list(super()._load_pos_data_fields(config) or [])

        # ✅ Core fields required by POS frontend (must exist)
        required = [
            "currency_id",
            "company_id",
            "name",
            "use_pricelist",
            "pricelist_id",
            "receipt_header",
            "receipt_footer",
        ]
        for fname in required:
            if fname not in fields_to_load:
                fields_to_load.append(fname)

        # ✅ Your custom fields
        extra = ["is_custom_receipt", "receipt_design_id", "design_receipt", "logo"]
        for fname in extra:
            if fname not in fields_to_load:
                fields_to_load.append(fname)

        return fields_to_load
