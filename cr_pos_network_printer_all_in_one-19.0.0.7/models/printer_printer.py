# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from odoo import models, fields, api


class Printer(models.Model):
    _inherit = 'printer.printer'

    ip = fields.Char(string='IP Address')
    port = fields.Integer(string='Port', default=9100)
    printer_type = fields.Selection(
        selection_add=[('network', 'IP/Network Printer'), ('usb', 'USB Printer')],
        ondelete={'network': 'set default', 'usb': 'set default'}
    )

    print_engine_key = fields.Char(related='print_engine_client_id.print_engine_key', string='Engine Key', readonly=True)

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'ip', 'port', 'printer_type', 'print_engine_key']

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _load_pos_data_search_read(self, data, config):
        domain = self._load_pos_data_domain(data, config)
        fields = self._load_pos_data_fields(config)
        return self.search_read(domain, fields, load=False)

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} [{record.print_engine_client_id.name}]"

    def action_test_printer(self):
        # Let the base zpl_office module create the print.job record
        res = super(Printer, self).action_test_printer()
        
        # Inject the POS network fields immediately into the newly created test job
        if isinstance(res, dict) and res.get('params', {}).get('next', {}).get('res_id'):
            job_id = res['params']['next']['res_id']
            job = self.env['print.job'].browse(job_id)
            if self.printer_type in ['network', 'usb']:
                job.write({
                    'ip': self.ip,
                    'port': self.port,
                    'printer_type': self.printer_type
                })
        return res
