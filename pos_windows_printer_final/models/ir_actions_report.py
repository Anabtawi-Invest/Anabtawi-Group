# -*- coding: utf-8 -*-
import base64
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    property_printer_id = fields.Many2one(
        "printer.printer",
        string="Default Direct Printer",
        help="Target Windows printer for direct printing of this report."
    )
    auto_print = fields.Boolean(
        string="Auto Print on Generation",
        default=False,
        help="Automatically send to printer when this report is generated."
    )

    def report_action(self, docids, data=None, config=True):
        if self.env.context.get("skip_direct_print_choice") or not (
            self.auto_print and self.property_printer_id
        ):
            return super().report_action(docids, data=data, config=config)

        if isinstance(docids, models.Model):
            res_ids = docids.ids
        elif isinstance(docids, int):
            res_ids = [docids]
        else:
            res_ids = [int(res_id) for res_id in (docids or [])]

        return {
            "type": "ir.actions.act_window",
            "name": _("Print Options"),
            "res_model": "report.print.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_docids_json": json.dumps(res_ids),
                "default_data_json": json.dumps(data or {}, default=str),
                "default_original_context_json": json.dumps(
                    dict(self.env.context), default=str
                ),
            },
        }

    def print_action_direct(self, res_ids, data=None, original_context=None):
        """
        Directly send PDF report to the configured target printer.
        """
        self.ensure_one()
        if not self.property_printer_id:
            raise UserError(_("No default printer configured for report: %s") % self.name)

        printer = self.property_printer_id
        pdf_content, _ = self.with_context(original_context or {})._render_qweb_pdf(
            self.report_name, res_ids, data=data
        )

        if not pdf_content:
            raise UserError(_("Failed to generate PDF content for report."))

        encoded_data = base64.b64encode(pdf_content).decode("utf-8")

        print_job = self.env["print.job"].create({
            "name": f"{self.name} - Direct Print",
            "printer_id": printer.id,
            "printer_name": printer.name,
            "image_data": encoded_data,
            "print_type": "image",
            "report_id": self.id,
            "print_engine_client_id": printer.print_engine_client_id.id if printer.print_engine_client_id else False,
            "print_engine_key": printer.print_engine_client_id.print_engine_key if printer.print_engine_client_id else False,
            "state": "draft",
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Report Sent to Printer"),
                "message": _("Report queued for printer: %s") % printer.name,
                "type": "success",
            }
        }
