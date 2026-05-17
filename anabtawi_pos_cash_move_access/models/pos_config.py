from odoo import api, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        has_custom_cash_move_group = self.env.user.has_group(
            "anabtawi_pos_cash_move_access.group_pos_cash_in_out"
        )
        if has_custom_cash_move_group:
            for record in read_records:
                record["_has_cash_move_perm"] = True
        return read_records
