from odoo import http
from odoo.http import request


class AiReportingReportBuilderController(http.Controller):

    @http.route("/ai_reporting/report_builder/create", type="json", auth="user")
    def create_request(self, question):
        report_request = request.env["ai.reporting.request"].create({"question": question})
        report_request.action_generate_draft()
        return {"id": report_request.id, "state": report_request.state, "preview": report_request.preview_result_metadata_json}

    @http.route("/ai_reporting/report_builder/adjust", type="json", auth="user")
    def adjust_request(self, request_id, adjustment):
        report_request = request.env["ai.reporting.request"].browse(int(request_id)).exists()
        if report_request:
            report_request.action_request_adjustment(adjustment)
        return {"id": report_request.id, "state": report_request.state, "preview": report_request.preview_result_metadata_json}

    @http.route("/ai_reporting/report_builder/confirm", type="json", auth="user")
    def confirm_request(self, request_id, name=None):
        report_request = request.env["ai.reporting.request"].browse(int(request_id)).exists()
        if report_request:
            report_request.action_confirm(name)
            report_request.action_save_report()
        return {"id": report_request.id, "state": report_request.state, "saved_report_id": report_request.saved_report_id.id}

