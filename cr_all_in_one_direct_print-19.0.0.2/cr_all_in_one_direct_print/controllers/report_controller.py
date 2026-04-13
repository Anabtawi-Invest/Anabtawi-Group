# -*- coding: utf-8 -*-
from odoo.addons.web.controllers.report import ReportController
from odoo import http
from odoo.http import request
import json
import base64
import logging
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import textwrap
from werkzeug.urls import url_parse
from odoo.http import content_disposition
from odoo.tools.misc import html_escape
from odoo.tools.safe_eval import safe_eval, time

_logger = logging.getLogger(__name__)


class ReportControllerInherit(ReportController):

    def _text_to_image(self, text, font_size=18, padding=20, max_width=1800):
        """
        Convert text content (e.g., ESC/POS raw text) into a PNG image.
        """
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        if isinstance(text, (bytes, bytearray)):
            text = text.decode("utf-8", errors="replace")

        wrapper = textwrap.TextWrapper(width=100)
        lines = []
        for line in text.splitlines() or [""]:
            lines.extend(wrapper.wrap(line) or [""])

        dummy = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(dummy)

        line_height = font.getbbox("Ay")[3]
        img_height = padding * 2 + line_height * len(lines)

        img = Image.new("RGB", (max_width, img_height), "white")
        draw = ImageDraw.Draw(img)

        y = padding
        for line in lines:
            draw.text((padding, y), line, fill="black", font=font)
            y += line_height

        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @http.route(
        [
            "/report/<converter>/<reportname>",
            "/report/<converter>/<reportname>/<docids>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def report_routes(self, reportname, docids=None, converter=None, **data):
        """
        Override standard report route to handle Auto-Print logic and Direct Print mode.

        Logic:
        - Normal Print (from Odoo) → Always download (standard behavior)
        - Direct Print (from our dropdown) → Print only, no download
        """
        report = request.env["ir.actions.report"]._get_report_from_name(reportname)

        context = dict(request.env.context)
        if data.get("context"):
            context.update(json.loads(data["context"]))

        direct_print_mode = context.get("direct_print_mode", False)

        if not direct_print_mode:
            return super().report_routes(reportname, docids, converter, **data)

        if not report:
            return super().report_routes(reportname, docids, converter, **data)

        if not getattr(report, "auto_print_enabled", False):

            return request.make_response(
                json.dumps(
                    {
                        "error": "Direct Print Not Configured",
                        "message": f"Please enable Auto-Print for the report '{report.name}' in Settings → Technical → Reports.",
                    }
                ),
                headers=[
                    ("Content-Type", "application/json"),
                ],
                status=400,
            )

        if not getattr(report, "default_printer_id", False):
            return request.make_response(
                json.dumps(
                    {
                        "error": "No Printer Configured",
                        "message": f"Please configure a default printer for the report '{report.name}' in Settings → Technical → Reports.",
                    }
                ),
                headers=[
                    ("Content-Type", "application/json"),
                ],
                status=400,
            )

        use_auto_print = True
        printer = report.default_printer_id

        if converter not in ("pdf", "html", "text"):
            return super().report_routes(reportname, docids, converter, **data)

        try:
            context = dict(request.env.context)
            original_docids = docids

            if docids:
                docids = [int(i) for i in getattr(docids, "split", lambda x: docids)(",")]

            if data.get("options"):
                data.update(json.loads(data.pop("options")))
            if data.get("context"):
                data["context"] = json.loads(data["context"])
                if data["context"].get("lang"):
                    del data["context"]["lang"]
                context.update(data["context"])

            if report.report_type == "qweb-text":
                text = report.with_context(context)._render_qweb_text(
                    reportname, docids, data=data
                )[0]

                if printer.printer_type == "raw":
                    job_data = base64.b64encode(text.encode("utf-8") if isinstance(text, str) else text)
                    print_type = "raw"
                else:
                    png_bytes = self._text_to_image(text)
                    job_data = base64.b64encode(png_bytes)
                    print_type = "image"

                request.env["print.job"].sudo().create(
                    {
                        "name": report.name,
                        "report_id": report.id,
                        "image_data": job_data,
                        "print_type": print_type,
                        "printer_id": printer.id,
                        "printer_name": printer.name,
                        "print_engine_client_id": (
                            printer.print_engine_client_id.id
                            if printer.print_engine_client_id
                            else False
                        ),
                        "print_engine_key": (
                            printer.print_engine_client_id.print_engine_key
                            if printer.print_engine_client_id
                            else False
                        ),
                        "state": "draft",
                    }
                )

                return request.make_response(
                    json.dumps(
                        {
                            "success": True,
                            "message": f"Report sent to printer: {printer.name}",
                            "printer": printer.name,
                            "report": report.name,
                        }
                    ),
                    headers=[("Content-Type", "application/json")],
                )

            if report.report_type == "qweb-html" and converter == "html":
                pdf_bytes = report.with_context(context)._render_qweb_pdf(
                    reportname, docids, data=data
                )[0]

                pdf = pdfium.PdfDocument(pdf_bytes)

                for page_number in range(len(pdf)):
                    page = pdf.get_page(page_number)
                    bitmap = page.render(scale=300 / 72)
                    image = bitmap.to_pil().convert("RGB")
                    bitmap.close()
                    page.close()

                    buf = BytesIO()
                    image.save(buf, format="PNG")

                    request.env["print.job"].sudo().create(
                        {
                            "name": f"{report.name} - Page {page_number + 1}",
                            "report_id": report.id,
                            "image_data": base64.b64encode(buf.getvalue()),
                            "printer_id": printer.id,
                            "printer_name": printer.name,
                            "print_engine_client_id": (
                                printer.print_engine_client_id.id
                                if printer.print_engine_client_id
                                else False
                            ),
                            "print_engine_key": (
                                printer.print_engine_client_id.print_engine_key
                                if printer.print_engine_client_id
                                else False
                            ),
                            "state": "draft",
                        }
                    )

                pdf.close()

                return request.make_response(
                    json.dumps(
                        {
                            "success": True,
                            "message": f"Report sent to printer: {printer.name}",
                            "printer": printer.name,
                            "report": report.name,
                        }
                    ),
                    headers=[("Content-Type", "application/json")],
                )

            pdf_bytes = report.with_context(context)._render_qweb_pdf(
                reportname, docids, data=data
            )[0]

            pdf = pdfium.PdfDocument(pdf_bytes)

            for page_number in range(len(pdf)):
                page = pdf.get_page(page_number)
                bitmap = page.render(scale=300 / 72)
                image = bitmap.to_pil().convert("RGB")
                bitmap.close()
                page.close()

                buf = BytesIO()
                image.save(buf, format="PNG")
                image_base64 = base64.b64encode(buf.getvalue())

                vals = {
                    "name": f"{report.name} - Page {page_number + 1}",
                    "report_id": report.id,
                    "image_data": image_base64,
                    "printer_id": printer.id,
                    "printer_name": printer.name,
                    "print_engine_client_id": (
                        printer.print_engine_client_id.id
                        if printer.print_engine_client_id
                        else False
                    ),
                    "print_engine_key": (
                        printer.print_engine_client_id.print_engine_key
                        if printer.print_engine_client_id
                        else False
                    ),
                    "state": "draft",
                }

                request.env["print.job"].sudo().create(vals)

            pdf.close()

            return request.make_response(
                json.dumps(
                    {
                        "success": True,
                        "message": f"Report sent to printer: {printer.name}",
                        "printer": printer.name,
                        "report": report.name,
                    }
                ),
                headers=[
                    ("Content-Type", "application/json"),
                ],
            )
        except Exception:
            _logger.exception("Auto print failed")
            return super().report_routes(reportname, docids, converter, **data)

    @http.route(["/report/download"], type="http", auth="user")
    def report_download(self, data, context=None, token=None, readonly=True):
        """
        Override report download to handle Direct Print mode.

        When direct_print_mode is in context:
        - Block the download
        - Return a message that print job was created

        For normal prints:
        - Allow standard Odoo download behavior
        """

        requestcontent = json.loads(data)
        url, type_ = requestcontent[0], requestcontent[1]

        try:
            if type_ in ["qweb-pdf", "qweb-text"]:
                pattern = "/report/pdf/" if type_ == "qweb-pdf" else "/report/text/"
                reportname = url.split(pattern)[1].split("?")[0]

                if "/" in reportname:
                    reportname = reportname.split("/")[0]

                from werkzeug.urls import url_parse

                data_dict = url_parse(url).decode_query(cls=dict)

                context_data = json.loads(context or "{}")
                if "context" in data_dict:
                    url_context = json.loads(data_dict.get("context", "{}"))
                    context_data.update(url_context)

                if context_data.get("direct_print_mode"):

                    return request.make_response(
                        json.dumps(
                            {
                                "success": True,
                                "message": "Report sent to printer. Download blocked in Direct Print mode.",
                                "direct_print": True,
                            }
                        ),
                        headers=[
                            ("Content-Type", "application/json"),
                        ],
                    )

        except Exception as e:
            _logger.warning(f"Error checking direct print mode: {e}")

        return super().report_download(data, context, token, readonly)
