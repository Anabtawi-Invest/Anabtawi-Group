from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    is_gift = fields.Boolean(string="Gift", default=False)
    gift_reason = fields.Char(string="Gift Reason")

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        if "is_gift" not in fields_to_load:
            fields_to_load.append("is_gift")
        if "gift_reason" not in fields_to_load:
            fields_to_load.append("gift_reason")
        return fields_to_load
