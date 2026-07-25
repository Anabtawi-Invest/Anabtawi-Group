# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class CrPrinterController(http.Controller):

    @http.route("/verify/api", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def verify_api_token(self, **kwargs):
        api_token = request.httprequest.headers.get("Authorization")
        if not api_token:
            return {"status": "error", "message": "Missing Authorization header"}

        param_key = request.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key", "")
        if api_token not in param_key:
            return {"status": "error", "message": "Invalid API token"}

        params = request.params or kwargs
        printers_data = params.get("printers", [])

        if printers_data:
            client = request.env["print.engine.client"].sudo().search(
                [("print_engine_key", "=", api_token)], limit=1
            )
            if client:
                sync_result = client.sync_printers_from_engine(printers_data)
                return {
                    "status": "success",
                    "message": "Token verified",
                    "created": sync_result.get("created", 0),
                    "updated": sync_result.get("updated", 0),
                }

        return {"status": "success", "message": "Token verified"}

    @http.route("/api/print_job", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def print_jobs(self, **kwargs):
        api_token = request.httprequest.headers.get("Authorization")
        param_key = request.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key", "")

        if not param_key or not api_token or api_token not in param_key:
            return []

        PrintJob = request.env["print.job"].sudo()
        jobs = PrintJob.search(
            [("state", "=", "draft"), ("print_engine_key", "=", api_token)],
            order="id asc"
        )

        if jobs:
            jobs.write({"state": "printing"})

        return jobs.read(["id", "image_data", "printer_name", "print_type"])

    @http.route("/api/print_job/update_status", type="jsonrpc", auth="none", csrf=False, methods=["POST"])
    def update_multiple_statuses(self, **kwargs):
        api_token = request.httprequest.headers.get("Authorization")
        param_key = request.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key", "")

        if not param_key or not api_token or api_token not in param_key:
            return {"status": "error", "message": "Invalid API token"}

        params = request.params or kwargs
        jobs = params.get("jobs", [])

        if not jobs:
            return {"status": "error", "message": "No jobs provided"}

        PrintJob = request.env["print.job"].sudo()
        for job in jobs:
            job_id = job.get("id")
            state = job.get("state")
            error_message = job.get("error_message", "")
            if job_id and state:
                PrintJob.browse(job_id).write({"state": state, "error_message": error_message})

        return {"status": "success", "message": f"{len(jobs)} jobs updated"}

    @http.route("/api/sync_printers", type="jsonrpc", auth="none", csrf=False, methods=["POST"])
    def sync_printers(self, **kwargs):
        api_token = request.httprequest.headers.get("Authorization")
        param_key = request.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key", "")

        if not param_key or not api_token or api_token not in param_key:
            return {"status": "error", "message": "Invalid API token"}

        params = request.params or kwargs
        printers_data = params.get("printers", [])

        if not printers_data:
            return {"status": "warning", "message": "No printers provided"}

        client = request.env["print.engine.client"].sudo().search(
            [("print_engine_key", "=", api_token)], limit=1
        )

        if not client:
            return {"status": "error", "message": "Print engine client not found"}

        return client.sync_printers_from_engine(printers_data)
