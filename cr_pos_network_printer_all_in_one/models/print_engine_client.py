# -*- coding: utf-8 -*-
# Part of Creyox Technologies

import secrets
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PrintEngineClient(models.Model):
    _inherit = 'print.engine.client'

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'print_engine_key']

    @api.model
    def _load_pos_data_domain(self, data, config):
        printer_ids = config.printer_ids.mapped('printer_id')
        if config.printer_id:
            printer_ids |= config.printer_id
        client_ids = printer_ids.mapped('print_engine_client_id').ids
        return [('id', 'in', client_ids)]

    @api.model
    def _load_pos_data_search_read(self, data, config):
        domain = self._load_pos_data_domain(data, config)
        fields = self._load_pos_data_fields(config)
        return self.search_read(domain, fields, load=False)
