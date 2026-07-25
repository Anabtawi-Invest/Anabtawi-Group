# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class CrPrinterController(http.Controller):

    @staticmethod
    def _get_authorized_client():
        """Return the active client matching the complete bearer token."""
        api_token = (request.httprequest.headers.get("Authorization") or "").strip()
        if not api_token:
            return request.env["print.engine.client"]
        return request.env["print.engine.client"].sudo().search(
            [("print_engine_key", "=", api_token), ("active", "=", True)],
            limit=1,
        )

    @http.route("/verify/api", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def verify_api_token(self, **kwargs):
        client = self._get_authorized_client()
        if not client:
            return {"status": "error", "message": "Invalid API token"}

        params = request.params or kwargs or {}
        printers_data = params.get("printers", [])

        if printers_data:
            sync_result = client.sync_printers_from_engine(printers_data)
            return {
                "status": "success",
                "message": "Token verified",
                "created": sync_result.get("created", 0),
                "updated": sync_result.get("updated", 0),
                "archived": sync_result.get("archived", 0),
            }

        return {"status": "success", "message": "Token verified"}

    @http.route("/api/print_job", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def print_jobs(self, **kwargs):
        client = self._get_authorized_client()
        if not client:
            return []

        PrintJob = request.env["print.job"].sudo()
        jobs = PrintJob.search(
            [("state", "=", "draft"), ("print_engine_client_id", "=", client.id)],
            order="id asc",
            limit=50,
        )

        if jobs:
            jobs.write({"state": "printing"})

        return jobs.read([
            "id", "name", "image_data", "printer_name", "print_type",
            "is_open_cashbox",
        ])

    @http.route("/api/print_job/update_status", type="jsonrpc", auth="none", csrf=False, methods=["POST"])
    def update_multiple_statuses(self, **kwargs):
        client = self._get_authorized_client()
        if not client:
            return {"status": "error", "message": "Invalid API token"}

        params = request.params or kwargs or {}
        jobs = params.get("jobs", [])

        if not jobs:
            return {"status": "error", "message": "No jobs provided"}

        PrintJob = request.env["print.job"].sudo()
        updated = 0
        for job in jobs:
            job_id = job.get("id")
            state = job.get("state")
            error_message = job.get("error_message", "")
            if not job_id or state not in ("done", "error"):
                continue
            matching_job = PrintJob.search([
                ("id", "=", int(job_id)),
                ("print_engine_client_id", "=", client.id),
                ("state", "=", "printing"),
            ], limit=1)
            if matching_job:
                matching_job.write({
                    "state": state,
                    "error_message": error_message[:4000],
                })
                updated += 1

        return {"status": "success", "message": f"{updated} jobs updated"}

    @http.route("/api/sync_printers", type="jsonrpc", auth="none", csrf=False, methods=["POST"])
    def sync_printers(self, **kwargs):
        client = self._get_authorized_client()
        if not client:
            return {"status": "error", "message": "Invalid API token"}

        params = request.params or kwargs or {}
        printers_data = params.get("printers", [])

        if not printers_data:
            return {"status": "warning", "message": "No printers provided"}

        return client.sync_printers_from_engine(printers_data)
