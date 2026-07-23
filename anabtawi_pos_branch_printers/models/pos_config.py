# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    branch_printer_id = fields.Many2one(
        'pos.branch.printer',
        string='Branch Thermal Printer',
        help='Assigned LAN or USB thermal printer for this branch POS'
    )

    @api.onchange('branch_printer_id')
    def _onchange_branch_printer_id(self):
        if self.branch_printer_id:
            if self.branch_printer_id.printer_id:
                self.printer_id = self.branch_printer_id.printer_id.id
            self.other_devices = True

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        for config in configs:
            if config.branch_printer_id and config.branch_printer_id.printer_id:
                config.printer_id = config.branch_printer_id.printer_id.id
                config.other_devices = True
        return configs

    def write(self, vals):
        res = super().write(vals)
        if 'branch_printer_id' in vals:
            for config in self:
                if config.branch_printer_id and config.branch_printer_id.printer_id:
                    config.printer_id = config.branch_printer_id.printer_id.id
                    config.other_devices = True
        return res

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        if 'branch_printer_id' not in params:
            params.append('branch_printer_id')
        return params
