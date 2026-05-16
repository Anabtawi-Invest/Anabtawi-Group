# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from datetime import timedelta
from io import BytesIO
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class UserRecordActivityWizard(models.TransientModel):
    _name = "user.record.activity.wizard"
    _description = "User Record Activity Wizard"

    date_from = fields.Datetime(
        required=True,
        default=lambda self: fields.Datetime.now() - timedelta(days=7),
    )
    date_to = fields.Datetime(required=True, default=fields.Datetime.now)
    include_all_models = fields.Boolean(string="Include All Models")
    model_ids = fields.Many2many(
        "ir.model",
        string="Models",
        domain=[("transient", "=", False)],
        help="Choose which models to include in the report.",
    )

    def _get_target_models(self):
        self.ensure_one()
        model_obj = self.env["ir.model"].sudo()
        if self.include_all_models:
            return model_obj.search([("transient", "=", False)])
        return self.model_ids

    def _generate_xlsx(self, summary_rows, detail_rows):
        import xlsxwriter  # noqa: PLC0415

        with BytesIO() as output:
            with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:
                header_format = workbook.add_format({"bold": True, "bg_color": "#D9E1F2"})

                summary_sheet = workbook.add_worksheet("Summary")
                summary_headers = ["User", "Login", "Total Created Records"]
                for col_idx, header in enumerate(summary_headers):
                    summary_sheet.write(0, col_idx, header, header_format)
                for row_idx, row in enumerate(summary_rows, start=1):
                    summary_sheet.write(row_idx, 0, row["user_name"])
                    summary_sheet.write(row_idx, 1, row["login"])
                    summary_sheet.write_number(row_idx, 2, row["count"])
                summary_sheet.set_column(0, 1, 35)
                summary_sheet.set_column(2, 2, 20)

                detail_sheet = workbook.add_worksheet("Details")
                detail_headers = ["Model Name", "Technical Model", "User", "Login", "Created Records"]
                for col_idx, header in enumerate(detail_headers):
                    detail_sheet.write(0, col_idx, header, header_format)
                for row_idx, row in enumerate(detail_rows, start=1):
                    detail_sheet.write(row_idx, 0, row["model_name"])
                    detail_sheet.write(row_idx, 1, row["model"])
                    detail_sheet.write(row_idx, 2, row["user_name"])
                    detail_sheet.write(row_idx, 3, row["login"])
                    detail_sheet.write_number(row_idx, 4, row["count"])
                detail_sheet.set_column(0, 1, 35)
                detail_sheet.set_column(2, 3, 30)
                detail_sheet.set_column(4, 4, 18)

            return output.getvalue()

    def action_export_xlsx(self):
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_("Date From must be earlier than Date To."))

        target_models = self._get_target_models()
        if not target_models:
            raise UserError(_("Please select at least one model or enable Include All Models."))

        summary_by_user = defaultdict(int)
        detail_rows = []
        user_cache = {}

        for model_rec in target_models:
            model_name = model_rec.model
            model_class = self.env.registry.get(model_name)
            if not model_class:
                continue

            model = self.env[model_name].sudo().with_context(active_test=False)
            if model._transient or model._abstract or not model._auto:
                continue
            if "create_uid" not in model._fields or "create_date" not in model._fields:
                continue

            domain = [
                ("create_uid", "!=", False),
                ("create_date", ">=", self.date_from),
                ("create_date", "<=", self.date_to),
            ]
            try:
                grouped = model.read_group(domain, ["create_uid"], ["create_uid"], lazy=False)
            except Exception as error:  # noqa: BLE001
                _logger.warning("Skipping model %s due to error: %s", model_name, error)
                continue

            for row in grouped:
                user_data = row.get("create_uid")
                if not user_data:
                    continue
                user_id, user_name = user_data
                count = row.get("create_uid_count", row.get("__count", 0))
                summary_by_user[user_id] += count

                if user_id not in user_cache:
                    user = self.env["res.users"].sudo().browse(user_id)
                    user_cache[user_id] = {
                        "name": user.name or "",
                        "login": user.login or "",
                    }

                detail_rows.append({
                    "model_name": model_rec.name,
                    "model": model_name,
                    "user_name": user_cache[user_id]["name"] or user_name,
                    "login": user_cache[user_id]["login"],
                    "count": count,
                })

        if not detail_rows:
            raise UserError(_("No created records were found in the selected period and models."))

        summary_rows = [{
            "user_name": user_cache[user_id]["name"],
            "login": user_cache[user_id]["login"],
            "count": count,
        } for user_id, count in summary_by_user.items()]
        summary_rows.sort(key=lambda line: (-line["count"], line["user_name"]))
        detail_rows.sort(key=lambda line: (line["model_name"], -line["count"], line["user_name"]))

        file_content = self._generate_xlsx(summary_rows, detail_rows)
        filename = "user_record_activity_%s_%s.xlsx" % (
            self.date_from.strftime("%Y%m%d_%H%M%S"),
            self.date_to.strftime("%Y%m%d_%H%M%S"),
        )

        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "type": "binary",
            "raw": file_content,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
