# -*- coding: utf-8 -*-
import base64
import json

from odoo import _, fields, models
from odoo.exceptions import UserError


class TalabatImportWizard(models.TransientModel):
    _name = "talabat.import.wizard"
    _description = "Import Talabat Reviews JSON"

    data_file = fields.Binary(string="JSON file")
    data_filename = fields.Char()
    json_text = fields.Text(
        string="Or paste JSON",
        help='Format: {"stores":[{"vendor_id":"TB_JO;629658","name":"...","store_rating":3.8,'
             '"review_count":25,"one_star_count":16,"reviews":[{"order_number":"…",'
             '"review_datetime":"11/23/2026 07:37 AM","rating":1,"comment":"…",'
             '"lines":[{"product_name":"كنافة","quantity":1}]}]}]}',
    )

    def action_import(self):
        self.ensure_one()
        raw = ""
        if self.data_file:
            raw = base64.b64decode(self.data_file).decode("utf-8", errors="replace")
        elif self.json_text:
            raw = self.json_text
        else:
            raise UserError(_("Provide a JSON file or paste JSON text."))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UserError(_("Invalid JSON: %s") % exc) from exc
        stats = self.env["talabat.sync.mixin"].import_payload(payload)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Talabat import"),
                "message": _(
                    "Imported %(stores)s stores, %(reviews)s reviews, %(lines)s lines."
                ) % stats,
                "sticky": False,
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
