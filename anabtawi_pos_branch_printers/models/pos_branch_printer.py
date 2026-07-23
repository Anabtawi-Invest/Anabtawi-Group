# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosBranchPrinter(models.Model):
    _name = 'pos.branch.printer'
    _description = 'POS Branch Printer Mapping'
    _order = 'branch_code, name'

    name = fields.Char(string='Printer Name', required=True, help="e.g. Branch 01 - Thermal Receipt Printer")
    branch_code = fields.Char(string='Branch Code / ID', required=True, help="Unique identifier for the branch (e.g. B01, B02)")
    active = fields.Boolean(string='Active', default=True)

    connection_type = fields.Selection([
        ('lan', 'LAN / Network Printer (IP Address)'),
        ('usb', 'USB Thermal Printer'),
    ], string='Connection Type', default='lan', required=True)

    # LAN Settings
    ip_address = fields.Char(string='IP Address', help="IP address of the LAN printer (e.g., 192.168.1.100)")
    port = fields.Integer(string='Port', default=9100, help="Port of the LAN printer (default 9100 for RAW/ESC POS)")

    # USB Settings
    usb_vendor_id = fields.Char(string='USB Vendor ID', help="Hex Vendor ID (e.g. 0x04b8)")
    usb_product_id = fields.Char(string='USB Product ID', help="Hex Product ID (e.g. 0x0e15)")
    usb_device_name = fields.Char(string='USB Device Name', help="Device Name / Path (e.g. /dev/usb/lp0 or EPSON TM-T20)")

    # Integration fields
    print_engine_client_id = fields.Many2one('print.engine.client', string='Print Engine Client', help="Select the local Print Engine Client running at this branch")
    printer_id = fields.Many2one('printer.printer', string='Linked Direct Printer', ondelete='set null')
    pos_config_ids = fields.One2many('pos.config', 'branch_printer_id', string='Assigned POS Configurations')

    notes = fields.Text(string='Notes / Maintenance Log')

    _sql_constraints = [
        ('branch_code_unique', 'unique(branch_code)', 'Branch Code must be unique across all branch printers!'),
    ]

    @api.constrains('connection_type', 'ip_address')
    def _check_lan_ip(self):
        for record in self:
            if record.connection_type == 'lan' and not record.ip_address:
                raise ValidationError(_("IP Address is required for LAN Network Printers."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._sync_printer_record()
        return records

    def write(self, vals):
        res = super().write(vals)
        for record in self:
            record._sync_printer_record()
        return res

    def _sync_printer_record(self):
        """Creates or updates the underlying printer.printer record used by direct print engine."""
        self.ensure_one()
        printer_model = self.env['printer.printer']

        printer_type_map = 'network' if self.connection_type == 'lan' else 'usb'
        printer_vals = {
            'name': f"{self.branch_code} - {self.name}",
            'printer_type': printer_type_map,
            'ip': self.ip_address if self.connection_type == 'lan' else False,
            'port': self.port if self.connection_type == 'lan' else 9100,
        }

        if self.print_engine_client_id:
            printer_vals['print_engine_client_id'] = self.print_engine_client_id.id

        if self.printer_id:
            self.printer_id.write(printer_vals)
        else:
            new_printer = printer_model.create(printer_vals)
            self.with_context(tracking_disable=True).printer_id = new_printer.id

        # Also sync to assigned pos.config printer_id
        for pos_config in self.pos_config_ids:
            if pos_config.printer_id != self.printer_id:
                pos_config.printer_id = self.printer_id.id
                pos_config.other_devices = True

    def action_test_connection(self):
        """Triggers direct test print on the linked printer."""
        self.ensure_one()
        if not self.printer_id:
            self._sync_printer_record()
        if self.printer_id:
            return self.printer_id.action_test_printer()
        raise ValidationError(_("No linked printer found to test."))
