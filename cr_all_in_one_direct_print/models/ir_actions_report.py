# -*- coding: utf-8 -*-
# Part of Creyox Technologies
from odoo import models, fields, _
import json


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    auto_print_enabled = fields.Boolean(
        string="Enable Auto-Print",
        default=False,
        help="When enabled, this report can trigger automatic printing. "
        "When disabled, only manual printing is allowed.",
    )

    default_printer_id = fields.Many2one(
        "printer.printer",
        string="Default Printer",
        help="Default printer to use for this report. Overrides global default printer setting.",
    )

    def report_action(self, docids, data=None, config=True):
        """
        Override to intercept reports triggered from code/buttons.
        If auto_print is enabled, show a dialog asking user to choose:
        - Download (normal behavior)
        - Direct Print (send to printer)
        """
        print("self.env.context", self.env.context)
        print("docids", docids)
        print("data", data)
        if self.env.context.get("skip_print_wizard"):
            return super().report_action(docids, data, config)

        if self.auto_print_enabled and self.default_printer_id:

            # Normalize docids to a plain list of integers
            if isinstance(docids, models.Model):
                active_ids = docids.ids
            elif isinstance(docids, int):
                active_ids = [docids]
            elif isinstance(docids, list):
                active_ids = [int(i) for i in docids]
            else:
                active_ids = []

            # Preserve the FULL original caller context exactly as-is.
            # This includes active_ids, active_model, default_product_ids, etc.
            # that are required by QWeb templates like stock label layouts.
            original_context = dict(self.env.context)

            return {
                "type": "ir.actions.act_window",
                "name": _("Print Options"),
                "res_model": "report.print.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_report_id": self.id,
                    # Pass docids and data as JSON strings so they survive
                    # the round-trip through Odoo's JS frontend unchanged.
                    "default_wizard_docids_json": json.dumps(active_ids),
                    "default_wizard_data_json": json.dumps(data) if data else "{}",
                    "default_original_context_json": json.dumps(original_context),
                },
            }
        print("docids", docids)
        print("data", data)
        return super().report_action(docids, data, config)

    def action_view_print_jobs(self):
        """View all print jobs for this report."""
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": _("Print Jobs - %s") % self.name,
            "res_model": "print.job",
            "view_mode": "list,form",
            "domain": [("report_id", "=", self.id)],
            "target": "current",
        }
