# -*- coding: utf-8 -*-
import io
import base64
import socket
import logging
from PIL import Image

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


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
    port = fields.Integer(string='Port', default=9100, help="RAW ESC/POS Port (default 9100)")

    # USB Settings
    usb_vendor_id = fields.Char(string='USB Vendor ID', help="Hex Vendor ID (e.g. 0x04b8)")
    usb_product_id = fields.Char(string='USB Product ID', help="Hex Product ID (e.g. 0x0e15)")
    usb_device_name = fields.Char(string='USB Device Name', help="Device Path / Name (e.g. /dev/usb/lp0)")

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

    # =========================================================================
    # ESC/POS Thermal Printing Engine Methods
    # =========================================================================
    def _get_cashdrawer_bytes(self):
        """Standard ESC/POS Cash Drawer pulse command (Pin 2)."""
        return b'\x1b\x70\x00\x19\xfa'

    def _get_cut_bytes(self):
        """Standard ESC/POS Paper Feed & Partial Cut command."""
        return b'\x1b\x64\x03\x1d\x56\x41\x03'

    def _image_to_escpos(self, base64_image_data):
        """Converts base64 PNG/JPEG receipt image into ESC/POS GS v 0 raster command bytes."""
        if not base64_image_data:
            return b''

        # Handle data URI prefix if present
        if ',' in base64_image_data:
            base64_image_data = base64_image_data.split(',')[1]

        image_bytes = base64.b64decode(base64_image_data)
        img = Image.open(io.BytesIO(image_bytes)).convert('L')

        width, height = img.size

        # Width must be multiple of 8 for raster format
        width_bytes = (width + 7) // 8
        real_width = width_bytes * 8

        # Create 1-bit monochrome image
        img_mono = img.point(lambda p: 0 if p < 160 else 255, mode='1')

        # GS v 0 command header: GS v 0 m xL xH yL yH
        # m = 0 (normal mode)
        xl = width_bytes & 0xFF
        xh = (width_bytes >> 8) & 0xFF
        yl = height & 0xFF
        yh = (height >> 8) & 0xFF

        header = bytes([0x1D, 0x76, 0x30, 0x00, xl, xh, yl, yh])

        # Convert image pixels to ESC/POS raster byte stream
        raster_data = bytearray()
        pixels = img_mono.load()

        for y in range(height):
            for x_byte in range(width_bytes):
                byte_val = 0
                for bit in range(8):
                    x = x_byte * 8 + bit
                    if x < width:
                        if pixels[x, y] == 0:  # Black pixel
                            byte_val |= (1 << (7 - bit))
                raster_data.append(byte_val)

        # Initialize printer + raster image + feed lines + cut
        payload = b'\x1b\x40' + header + bytes(raster_data) + self._get_cut_bytes()
        return payload

    def send_raw_bytes(self, payload, timeout=6):
        """Sends raw ESC/POS bytes over socket connection to LAN Printer IP:Port."""
        self.ensure_one()
        if self.connection_type != 'lan' or not self.ip_address:
            raise UserError(_("Printer '%s' does not have a valid LAN IP address.") % self.name)

        port = self.port or 9100
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect((self.ip_address, port))
                sock.sendall(payload)
            _logger.info("Direct print payload sent successfully to %s:%s for branch %s", self.ip_address, port, self.branch_code)
            return True
        except Exception as e:
            _logger.error("Failed to connect to LAN printer at %s:%s for branch %s. Error: %s", self.ip_address, port, self.branch_code, str(e))
            raise UserError(_("Cannot connect to Thermal Printer at IP %(ip)s:%(port)s for Branch %(branch)s. Error: %(err)s") % {
                'ip': self.ip_address,
                'port': port,
                'branch': self.branch_code,
                'err': str(e),
            })

    @api.model
    def send_print_job(self, pos_config_id, image_data=False, is_open_cashbox=False):
        """
        API method invoked from POS JS.
        Validates branch ownership and sends direct ESC/POS print job.
        """
        if not pos_config_id:
            raise UserError(_("POS Configuration ID is required."))

        pos_config = self.env['pos.config'].browse(pos_config_id)
        if not pos_config.exists():
            raise UserError(_("Invalid POS Configuration."))

        branch_printer = pos_config.branch_printer_id
        if not branch_printer:
            _logger.warning("POS Config '%s' does not have a Branch Thermal Printer configured.", pos_config.name)
            return {'result': False, 'error': _("No thermal printer configured for this branch.")}

        payload = bytearray()

        if is_open_cashbox:
            payload.extend(branch_printer._get_cashdrawer_bytes())

        if image_data:
            payload.extend(branch_printer._image_to_escpos(image_data))

        if not payload:
            return {'result': True, 'error': False}

        try:
            branch_printer.send_raw_bytes(bytes(payload))
            return {'result': True, 'error': False}
        except Exception as err:
            return {'result': False, 'error': str(err)}

    def action_test_connection(self):
        """Sends a test page receipt to the assigned LAN thermal printer."""
        self.ensure_one()
        if self.connection_type != 'lan' or not self.ip_address:
            raise ValidationError(_("Test Print is only available for LAN Printers with an IP address."))

        # Build simple text test receipt payload
        header = f"\x1b\x40\x1b\x61\x01\x1b\x21\x30========================\nTEST PRINT SUCCESS\n========================\n\x1b\x21\x00Branch: {self.branch_code}\nPrinter: {self.name}\nIP: {self.ip_address}:{self.port}\nStatus: ONLINE & READY\n------------------------\n\n\n".encode('utf-8')
        payload = header + self._get_cut_bytes()

        self.send_raw_bytes(payload)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test Print Sent'),
                'message': _('Test print successfully sent to %s (%s:%s)') % (self.name, self.ip_address, self.port),
                'type': 'success',
            }
        }
