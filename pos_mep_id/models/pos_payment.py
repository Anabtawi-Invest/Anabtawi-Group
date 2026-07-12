# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    meps_rrn = fields.Char(string="MEPS RRN")
    meps_auth_code = fields.Char(string="MEPS Auth Code")
    meps_resp_code = fields.Char(string="MEPS Response Code")
    meps_resp_text = fields.Char(string="MEPS Response Text")
    meps_card_pan = fields.Char(string="MEPS Card (masked)")
    meps_card_entry_mode = fields.Char(string="MEPS Card Entry Mode")
    meps_batch_number = fields.Char(string="MEPS Batch Number")
    meps_stan = fields.Char(string="MEPS STAN")

    _MEPS_FIELDS = (
        "meps_rrn",
        "meps_auth_code",
        "meps_resp_code",
        "meps_resp_text",
        "meps_card_pan",
        "meps_card_entry_mode",
        "meps_batch_number",
        "meps_stan",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        for field_name in self._MEPS_FIELDS:
            if field_name not in fields_to_load:
                fields_to_load.append(field_name)
        return fields_to_load
