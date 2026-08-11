# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PosReportingDashboardController(http.Controller):

    @http.route(
        "/pos_unified_report/xlsx/<int:wizard_id>",
        type="http",
        auth="user",
    )
    def download_unified_report_xlsx(self, wizard_id, **kwargs):
        wizard = request.env["pos.unified.report.wizard"].browse(wizard_id)
        if not wizard.exists():
            return request.not_found()

        content = wizard._generate_xlsx_content()
        filename = f"POS_Unified_Operations_Report_{wizard.date_from}_{wizard.date_to}.xlsx"

        return request.make_response(
            content,
            headers=[
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", http.content_disposition(filename)),
            ],
        )
