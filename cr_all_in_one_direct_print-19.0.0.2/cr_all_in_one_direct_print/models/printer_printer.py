# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import logging

_logger = logging.getLogger(__name__)


class Printer(models.Model):
    _name = "printer.printer"
    _description = "PoS Printers"
    _rec_name = "name"

    name = fields.Char(string="Name", required=True)
    display_name = fields.Char(compute="_compute_display_name")
    print_engine_client_id = fields.Many2one(
        "print.engine.client", string="Host", ondelete="cascade"
    )
    printer_type = fields.Selection(
        [
            ("image", "Standard Printer (Image/PDF)"),
            ("raw", "Zebra / Raw Text Printer"),
        ],
        string="Printer Type",
        default="image",
        required=True,
        help="Standard printers convert all documents to images. Zebra/Raw printers send text/ZPL directly.",
    )

    def _compute_display_name(self):
        for record in self:
            record.display_name = (
                f"{record.name} [{record.print_engine_client_id.name}]"
            )

    def _generate_test_page_image(self):
        """
        Generate a branded, bold test page image for printer testing.
        Returns base64 encoded image data.
        """
        self.ensure_one()

        width = 384
        height = 650

        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)

        def load_font(name, size):
            try:
                return ImageFont.truetype(name, size)
            except:
                return ImageFont.load_default()

        font_header = load_font("arialbd.ttf", 30)
        font_subheader = load_font("arialbd.ttf", 20)
        font_medium = load_font("arial.ttf", 18)
        font_small = load_font("arial.ttf", 14)

        def draw_bold_centered(text, y, font, fill="black"):
            x = width // 2
            for dx, dy in [(0, 0), (1, 0), (0, 1)]:
                draw.text((x + dx, y + dy), text, fill=fill, font=font, anchor="mt")

        y = 20

        draw_bold_centered("CREYOX TECHNOLOGIES", y, font_header)
        y += 40

        draw_bold_centered("Connector Test Page", y, font_subheader)
        y += 30

        draw.line([(20, y), (width - 20, y)], fill="black", width=2)
        y += 25

        info_lines = [
            f"Printer Name : {self.name}",
            f"Host         : {self.print_engine_client_id.name}",
        ]

        for line in info_lines:
            draw.text((20, y), line, fill="black", font=font_medium)
            y += 28

        y += 10
        draw.line([(20, y), (width - 20, y)], fill="black", width=2)
        y += 30

        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        draw.text(
            (width // 2, y),
            f"Printed on: {timestamp}",
            fill="black",
            font=font_small,
            anchor="mt",
        )
        y += 25

        draw_bold_centered("TEST SUCCESSFUL", y, font_subheader)

        y += 40

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def action_test_printer(self):
        """
        Test printer connection by sending a test page.
        Creates a print job with a test image.
        """
        self.ensure_one()

        if not self.print_engine_client_id:
            raise UserError(_("No Print Engine Client assigned to this printer."))

        if not self.print_engine_client_id.print_engine_key:
            raise UserError(_("Print Engine Client has no key configured."))

        try:

            if self.printer_type == "raw":
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
                raw_text = (
                    "^XA\n" 
                    
                    f"^FO60,60^A0N,20,20^FDPrinter: {self.name[:15]}^FS\n"
                    f"^FO60,90^A0N,20,20^FDOn: {timestamp}^FS\n"
                    "^FO60,130^A0N,20,20^FD-----------------^FS\n"
                    "^FO60,160^A0N,25,25^FDTEST SUCCESSFUL^FS\n"
                    "^XZ\n"
                )
                test_data = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
                print_type = "raw"
            else:
                test_image = self._generate_test_page_image()
                test_data = test_image
                print_type = "image"

            print_job = self.env["print.job"].create(
                {
                    "name": f"Test Print - {self.name}",
                    "printer_id": self.id,
                    "printer_name": self.name,
                    "image_data": test_data,
                    "print_type": print_type,
                    "print_engine_client_id": (
                        self.print_engine_client_id.id
                        if self.print_engine_client_id
                        else False
                    ),
                    "print_engine_key": (
                        self.print_engine_client_id.print_engine_key
                        if self.print_engine_client_id
                        else False
                    ),
                    "state": "draft",
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Test Print Sent"),
                    "message": _(
                        "Test page has been queued for printing. Check the print job status to verify."
                    ),
                    "type": "success",
                    "sticky": False,
                    "next": {
                        "type": "ir.actions.act_window",
                        "res_model": "print.job",
                        "res_id": print_job.id,
                        "views": [[False, "form"]],
                        "target": "current",
                    },
                },
            }

        except Exception as e:
            _logger.exception(
                f"Failed to create test print job for printer {self.name}"
            )
            raise UserError(_("Failed to create test print job: %s") % str(e))
