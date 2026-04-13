# -*- coding: utf-8 -*-
# Part of Creyox Technologies
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import json
from io import BytesIO
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
import textwrap


class ReportPrintWizard(models.TransientModel):
    _name = "report.print.wizard"
    _description = "Report Print Options Wizard"

    report_id = fields.Many2one("ir.actions.report", string="Report", required=True)
    print_mode = fields.Selection(
        [
            ("download", "Download PDF"),
            ("direct_print", "Direct Print"),
        ],
        string="Print Mode",
        default="download",
        required=True,
    )

    auto_print_enabled = fields.Boolean(
        related="report_id.auto_print_enabled", readonly=True
    )
    default_printer_id = fields.Many2one(
        related="report_id.default_printer_id", readonly=True
    )

    # These three fields carry all necessary call-site data across the JS boundary
    # as plain JSON strings, so nothing is corrupted or lost by the frontend.
    wizard_docids_json = fields.Text(string="Docids JSON")
    wizard_data_json = fields.Text(string="Data JSON")
    original_context_json = fields.Text(string="Original Context JSON")

    # ─── Helper ──────────────────────────────────────────────────────────────

    def _text_to_image(self, text, font_size=18, padding=20, max_width=1800):
        """Convert plain text (e.g. ESC/POS) into a PNG image."""
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

    # ─── Action ──────────────────────────────────────────────────────────────

    def action_execute(self):
        """Execute the report based on selected print mode."""
        self.ensure_one()

        # --- Restore docids ------------------------------------------------
        # wizard_docids_json holds docids that were passed to report_action().
        # If it is empty (many wizards like stock label layout pass None),
        # fall back to active_ids from the original caller context, which is
        # always correct because Odoo sets active_ids to the selected records
        # before calling report_action().
        docids = json.loads(self.wizard_docids_json) if self.wizard_docids_json else []

        orig_ctx = {}
        if self.original_context_json:
            try:
                orig_ctx = json.loads(self.original_context_json)
            except Exception:
                orig_ctx = {}

        if not docids:
            docids = orig_ctx.get("active_ids") or []

        # --- Restore data --------------------------------------------------
        data = json.loads(self.wizard_data_json) if self.wizard_data_json else {}

        if not docids and not data:
            raise UserError(_("No records selected for printing."))

        # --- Dispatch -------------------------------------------------------
        if self.print_mode == "direct_print":
            if not self.auto_print_enabled:
                raise UserError(
                    _("Direct Print is not enabled for this report. "
                      "Please enable it in report settings.")
                )
            if not self.default_printer_id:
                raise UserError(
                    _("No default printer configured for this report. "
                      "Please configure one in report settings.")
                )
            return self._execute_direct_print(docids, data, orig_ctx)
        else:
            return self._execute_download(docids, data, orig_ctx)

    # ─── Direct Print ────────────────────────────────────────────────────────

    def _execute_direct_print(self, docids, data, orig_ctx):
        """Render the report and create a print.job record."""
        printer = self.default_printer_id
        report = self.report_id

        # Build the render context:
        #  1. Start from the original caller context (has active_ids, active_model,
        #     default_product_ids, etc. exactly as they were when Print was clicked).
        #  2. Overlay any extra context key from data['context'] if present.
        #  3. Always ensure active_ids / active_id / active_model are correct.
        context = dict(orig_ctx)

        if data and data.get("context"):
            ctx_extra = data["context"]
            if isinstance(ctx_extra, str):
                try:
                    ctx_extra = json.loads(ctx_extra)
                except Exception:
                    ctx_extra = {}
            if isinstance(ctx_extra, dict):
                context.update(ctx_extra)

        # Guarantee the active record pointers match the docids we resolved
        if docids:
            context["active_ids"] = docids
            context["active_id"] = docids[0]
        if data.get("active_model"):
            context["active_model"] = data["active_model"]

        try:
            if report.report_type == "qweb-text":
                text = report.with_context(context)._render_qweb_text(
                    report.report_name, docids, data=data
                )[0]

                if printer.printer_type == "raw":
                    job_data = base64.b64encode(
                        text.encode("utf-8") if isinstance(text, str) else text
                    )
                    print_type = "raw"
                else:
                    png_bytes = self._text_to_image(text)
                    job_data = base64.b64encode(png_bytes)
                    print_type = "image"

            else:
                pdf_content = report.with_context(context)._render_qweb_pdf(
                    report.report_name, docids, data=data
                )[0]

                pdf = pdfium.PdfDocument(pdf_content)
                pages_data = []
                for page_number in range(len(pdf)):
                    page = pdf.get_page(page_number)
                    bitmap = page.render(scale=300 / 72)
                    image = bitmap.to_pil().convert("RGB")
                    bitmap.close()
                    page.close()
                    buf = BytesIO()
                    image.save(buf, format="PNG")
                    pages_data.append(base64.b64encode(buf.getvalue()))
                pdf.close()

                # Create one print.job per page
                for idx, img_b64 in enumerate(pages_data):
                    self.env["print.job"].create({
                        "name": f"{report.name} - Page {idx + 1}",
                        "report_id": report.id,
                        "image_data": img_b64,
                        "print_type": "image",
                        "printer_id": printer.id,
                        "printer_name": printer.name,
                        "print_engine_client_id": (
                            printer.print_engine_client_id.id
                            if printer.print_engine_client_id else False
                        ),
                        "print_engine_key": (
                            printer.print_engine_client_id.print_engine_key
                            if printer.print_engine_client_id else False
                        ),
                        "state": "draft",
                    })

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Sent to Printer"),
                        "message": _("Report %s has been sent to %s.")
                        % (report.name, printer.name),
                        "sticky": False,
                        "type": "success",
                    },
                }

            # Single job for qweb-text
            self.env["print.job"].create({
                "name": report.name,
                "report_id": report.id,
                "image_data": job_data,
                "print_type": print_type,
                "printer_id": printer.id,
                "printer_name": printer.name,
                "print_engine_client_id": (
                    printer.print_engine_client_id.id
                    if printer.print_engine_client_id else False
                ),
                "print_engine_key": (
                    printer.print_engine_client_id.print_engine_key
                    if printer.print_engine_client_id else False
                ),
                "state": "draft",
            })

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sent to Printer"),
                    "message": _("Report %s has been sent to %s.")
                    % (report.name, printer.name),
                    "sticky": False,
                    "type": "success",
                },
            }

        except Exception as e:
            raise UserError(_("Error printing report: %s") % str(e))

    # ─── Download ────────────────────────────────────────────────────────────

    def _execute_download(self, docids, data, orig_ctx):
        """Fall back to the standard Odoo download flow."""
        # Restore the original context so the native report_action renders
        # correctly (e.g. layout_wizard, quantity_by_product are in data).
        return (
            self.report_id
            .with_context(orig_ctx, skip_print_wizard=True)
            .report_action(docids or None, data=data or None)
        )
