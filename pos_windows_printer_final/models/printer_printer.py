# -*- coding: utf-8 -*-
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class Printer(models.Model):
    _name = "printer.printer"
    _description = "Printers (Windows, Network, USB & Bluetooth)"
    _rec_name = "display_name"

    name = fields.Char(string="Printer Name", required=True)
    active = fields.Boolean(default=True)
    display_name = fields.Char(compute="_compute_display_name", store=True)
    print_engine_client_id = fields.Many2one(
        "print.engine.client",
        string="Windows Host PC",
        ondelete="cascade",
        help="Windows Host Computer running the Print Agent for this printer."
    )
    ip = fields.Char(string="IP Address / Hostname")
    port = fields.Integer(string="Port", default=9100)
    printer_type = fields.Selection(
        [
            ("image", "Standard Windows Printer (Image/PDF)"),
            ("raw", "Zebra / Raw Text Printer (ZPL)"),
            ("network", "Direct Network Printer (LAN ePOS)"),
            ("usb", "Direct USB / Local Printer"),
            ("bluetooth", "Bluetooth Printer (Mobile / Web Bluetooth)"),
        ],
        string="Printer Type",
        default="image",
        required=True
    )
    print_engine_key = fields.Char(
        related="print_engine_client_id.print_engine_key",
        string="Engine Key",
        readonly=True
    )

    @api.depends("name", "print_engine_client_id.name")
    def _compute_display_name(self):
        for record in self:
            if record.print_engine_client_id:
                record.display_name = f"{record.name} [{record.print_engine_client_id.name}]"
            else:
                record.display_name = record.name

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'ip', 'port', 'printer_type', 'print_engine_key']

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("active", "=", True)]

    @api.model
    def _load_pos_data_search_read(self, data, config):
        domain = self._load_pos_data_domain(data, config)
        fields = self._load_pos_data_fields(config)
        return self.search_read(domain, fields, load=False)

    def _generate_test_page_image(self):
        self.ensure_one()
        width, height = 384, 600
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)

        try:
            font_title = ImageFont.truetype("arialbd.ttf", 26)
            font_medium = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            font_title = ImageFont.load_default()
            font_medium = ImageFont.load_default()

        y = 20
        draw.text((width // 2, y), "ODOO PRINT AGENT", fill="black", font=font_title, anchor="mt")
        y += 40
        draw.text((width // 2, y), "Connector Test Page", fill="black", font=font_medium, anchor="mt")
        y += 35
        draw.line([(20, y), (width - 20, y)], fill="black", width=2)
        y += 25

        host_name = self.print_engine_client_id.name if self.print_engine_client_id else "Direct Local"
        draw.text((20, y), f"Printer : {self.name}", fill="black", font=font_medium)
        y += 30
        draw.text((20, y), f"Host    : {host_name}", fill="black", font=font_medium)
        y += 30
        draw.text((20, y), f"Type    : {dict(self._fields['printer_type'].selection).get(self.printer_type)}", fill="black", font=font_medium)
        y += 35
        draw.line([(20, y), (width - 20, y)], fill="black", width=2)
        y += 30

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((width // 2, y), f"Date: {timestamp}", fill="black", font=font_medium, anchor="mt")
        y += 35
        draw.text((width // 2, y), "*** TEST SUCCESSFUL ***", fill="black", font=font_title, anchor="mt")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def action_test_printer(self):
        self.ensure_one()
        if self.printer_type == "raw":
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            raw_text = (
                "^XA\n"
                f"^FO50,50^A0N,25,25^FDPrinter: {self.name[:15]}^FS\n"
                f"^FO50,90^A0N,20,20^FDOn: {timestamp}^FS\n"
                "^FO50,130^A0N,25,25^FDTEST SUCCESSFUL^FS\n"
                "^XZ\n"
            )
            test_data = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
            print_type = "raw"
        else:
            test_data = self._generate_test_page_image()
            print_type = "image"

        print_job = self.env["print.job"].create({
            "name": f"Test Print - {self.name}",
            "printer_id": self.id,
            "printer_name": self.name,
            "image_data": test_data,
            "print_type": print_type,
            "print_engine_client_id": self.print_engine_client_id.id if self.print_engine_client_id else False,
            "print_engine_key": self.print_engine_client_id.print_engine_key if self.print_engine_client_id else False,
            "ip": self.ip,
            "port": self.port,
            "state": "draft",
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Test Print Queued"),
                "message": _("Test page has been sent to the print queue."),
                "type": "success",
                "sticky": False,
            },
        }
