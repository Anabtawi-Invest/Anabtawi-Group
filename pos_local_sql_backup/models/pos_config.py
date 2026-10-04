# -*- coding: utf-8 -*-

from odoo import api, fields, models

LOCAL_BACKUP_FIELDS = ("local_backup_enabled", "local_backup_url", "local_backup_api_key")


class PosConfig(models.Model):
    _inherit = "pos.config"

    local_backup_enabled = fields.Boolean(
        string="Local SQL Backup",
        help="Copy every order to the Anabtawi POS Local Backup helper installed on the cashier PC.",
    )
    local_backup_url = fields.Char(
        string="Helper URL",
        default="http://127.0.0.1:8765",
    )
    local_backup_api_key = fields.Char(
        string="Helper API Key",
        help="Shown by the helper at the end of its setup (or with the 'show-config' command).",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        # Empty list means "load all fields".
        if fields_to_load:
            fields_to_load.extend(f for f in LOCAL_BACKUP_FIELDS if f not in fields_to_load)
        return fields_to_load
