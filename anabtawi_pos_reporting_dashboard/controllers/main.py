# -*- coding: utf-8 -*-
import logging
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosReportingDashboardController(http.Controller):

    @http.route(
        "/pos_unified_report/xlsx/<int:wizard_id>",
        type="http",
        auth="user",
    )
    def download_unified_report_xlsx(self, wizard_id, **kwargs):
        try:
            wizard = request.env["pos.unified.report.wizard"].sudo().browse(wizard_id)
            if not wizard.exists():
                return request.not_found()

            content = wizard._generate_xlsx_content()
            df_str = fields.Datetime.to_string(wizard.date_from).replace(" ", "_").replace(":", "-") if wizard.date_from else "start"
            dt_str = fields.Datetime.to_string(wizard.date_to).replace(" ", "_").replace(":", "-") if wizard.date_to else "end"
            filename = f"POS_Unified_Operations_Report_{df_str}_{dt_str}.xlsx"

            return request.make_response(
                content,
                headers=[
                    ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                    ("Content-Disposition", http.content_disposition(filename)),
                ],
            )
        except Exception as e:
            _logger.exception("Failed to generate Excel report for wizard %s: %s", wizard_id, e)
            return request.make_response(
                f"<html><body><h2>Error Generating Excel Report</h2><p>{str(e)}</p></body></html>",
                headers=[("Content-Type", "text/html")],
                status=500,
            )
