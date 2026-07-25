# -*- coding: utf-8 -*-
import json

from odoo import fields, models


class ReportPrintWizard(models.TransientModel):
    _name = "report.print.wizard"
    _description = "Choose Report Print Method"

    report_id = fields.Many2one("ir.actions.report", required=True, readonly=True)
    docids_json = fields.Text(required=True, default="[]")
    data_json = fields.Text(required=True, default="{}")
    original_context_json = fields.Text(required=True, default="{}")

    def action_direct_print(self):
        self.ensure_one()
        return self.report_id.print_action_direct(
            json.loads(self.docids_json or "[]"),
            data=json.loads(self.data_json or "{}"),
            original_context=json.loads(self.original_context_json or "{}"),
        )

    def action_download(self):
        self.ensure_one()
        context = json.loads(self.original_context_json or "{}")
        context["skip_direct_print_choice"] = True
        return self.report_id.with_context(context).report_action(
            json.loads(self.docids_json or "[]"),
            data=json.loads(self.data_json or "{}"),
        )
