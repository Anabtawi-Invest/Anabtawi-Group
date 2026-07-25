# -*- coding: utf-8 -*-
import base64
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

    def print_action_direct(self, res_ids):
        """
        Directly send PDF report to the configured target printer.
        """
        self.ensure_one()
        if not self.property_printer_id:
            raise UserError(_("No default printer configured for report: %s") % self.name)

        printer = self.property_printer_id
        pdf_content, _ = self._render_qweb_pdf(self.id, res_ids)

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
