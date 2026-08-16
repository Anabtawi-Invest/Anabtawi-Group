from odoo import api, models

RESTRICT_QTY_GROUP = "pos_restrict_qty_change.group_pos_restrict_qty_change"


class PosConfig(models.Model):
    _inherit = "pos.config"

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        is_restricted = self.env.user.has_group(RESTRICT_QTY_GROUP)
        for record in read_records:
            record["_restrict_pos_qty_change"] = is_restricted
        return read_records
