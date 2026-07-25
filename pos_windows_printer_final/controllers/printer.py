# -*- coding: utf-8 -*-
from odoo import http, api, SUPERUSER_ID
from odoo.http import request
import odoo

class WindowsPrinterAgentController(http.Controller):

    @staticmethod
    def _validate_api_token():
        """
        Safely validate Authorization header against print.engine.client and ir.config_parameter
        without leaving open database cursors.
        """
        api_token = request.httprequest.headers.get("Authorization")
        if not api_token:
            return False, "Missing Authorization header"

        try:
            # 1. Direct model check
            Client = request.env["print.engine.client"].sudo()
            if Client.search_count([("print_engine_key", "=", api_token)]) > 0:
                return True, "Token verified"

            # 2. System parameter fallback check
            param_obj = request.env["ir.config_parameter"].sudo()
            odoo_api_token = param_obj.get_param("cr_print_engine.key", "")
            if odoo_api_token:
                tokens_list = [k.strip() for k in odoo_api_token.split(",") if k.strip()]
                if api_token in tokens_list:
                    return True, "Token verified"

            return False, "Invalid API Token"
        except Exception as e:
            return False, str(e)

    @http.route("/verify/api", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def verify_api_token(self):
        """
        Endpoint to verify Windows Agent API token and sync local Windows installed printers.
        """
        valid, message = self._validate_api_token()
        if not valid:
            return {"status": "error", "message": message}

        try:
            printers_data = request.httprequest.json.get("printers", [])
            api_token = request.httprequest.headers.get("Authorization")

            if printers_data and api_token:
                PrintEngineClient = request.env["print.engine.client"].sudo()
                client = PrintEngineClient.search([("print_engine_key", "=", api_token)], limit=1)
                if client:
                    sync_res = client.sync_printers_from_engine(printers_data)
                    return {
                        "status": "success",
                        "message": message,
                        "created": sync_res.get("created", 0),
                        "updated": sync_res.get("updated", 0),
                    }
        except Exception as e:
            return {"status": "success", "message": message, "sync_error": str(e)}

        return {"status": "success", "message": message}

    @http.route("/api/print_job", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def fetch_print_jobs(self, **kwargs):
        """
        Fetch pending (draft) print jobs assigned to the requesting Windows Agent token.
        """
        valid, message = self._validate_api_token()
        if not valid:
            return []

        api_token = request.httprequest.headers.get("Authorization")
        PrintEngineClient = request.env["print.engine.client"].sudo()
        client = PrintEngineClient.search([("print_engine_key", "=", api_token)], limit=1)

        domain = [("state", "=", "draft")]
        if client:
            domain.extend([
                "|", "|",
                ("print_engine_key", "=", api_token),
                ("print_engine_client_id", "=", client.id),
                ("printer_id.print_engine_client_id", "=", client.id)
            ])
        else:
            domain.append(("print_engine_key", "=", api_token))

        PrintJob = request.env["print.job"].sudo()
        jobs = PrintJob.search(domain, order="id asc", limit=20)

        if jobs:
            jobs.write({"state": "printing"})

        return jobs.read(["id", "name", "image_data", "printer_name", "print_type", "is_open_cashbox"])

    @http.route("/api/print_job/update_status", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def update_job_status(self, **post):
        """
        Bulk or single status update from Windows Agent after printing completes/fails.
        """
        valid, message = self._validate_api_token()
        if not valid:
            return {"status": "error", "message": message}

        try:
            jobs = request.httprequest.json.get("jobs", [])
            if not jobs:
                return {"status": "error", "message": "No jobs provided"}

            PrintJob = request.env["print.job"].sudo()
            updated_ids = []

            for job_item in jobs:
                job_id = job_item.get("id")
                state = job_item.get("state")
                err_msg = job_item.get("error_message", "")
                if job_id and state:
                    job_rec = PrintJob.browse(job_id)
                    if job_rec.exists():
                        job_rec.write({"state": state, "error_message": err_msg})
                        updated_ids.append(job_id)

            return {"status": "success", "message": f"{len(updated_ids)} jobs updated", "job_ids": updated_ids}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @http.route("/api/sync_printers", type="jsonrpc", auth="none", methods=["POST"], csrf=False)
    def sync_printers(self, **post):
        """
        Explicitly sync local printers installed on Windows host.
        """
        valid, message = self._validate_api_token()
        if not valid:
            return {"status": "error", "message": message}

        try:
            printers_data = request.httprequest.json.get("printers", [])
            api_token = request.httprequest.headers.get("Authorization")
            PrintEngineClient = request.env["print.engine.client"].sudo()

            client = PrintEngineClient.search([("print_engine_key", "=", api_token)], limit=1)
            if not client:
                return {"status": "error", "message": "Host client not found for provided API key"}

            return client.sync_printers_from_engine(printers_data)
        except Exception as e:
            return {"status": "error", "message": str(e)}
