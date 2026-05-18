# -*- coding: utf-8 -*-
# Part of Creyox Technologies
from odoo import http, api, SUPERUSER_ID
from odoo.http import request
import odoo


class CrPrinterController(http.Controller):

    @staticmethod
    def _check_token_and_db():
        """Reusable method to validate token and DB"""
        db = request.httprequest.headers.get("X-Odoo-Db")
        api_token = request.httprequest.headers.get("Authorization")

        if not db or not api_token:
            return False, "Missing database or Authorization header"

        if db not in odoo.service.db.list_dbs(force=True):
            return False, "Database not found"

        try:
            registry = odoo.modules.registry.Registry(db)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                odoo_api_token = (
                    env["ir.config_parameter"].sudo().get_param("cr_print_engine.key")
                )
                if api_token in odoo_api_token:
                    return True, "Token verified"
                else:
                    return False, "Invalid token"
        except Exception as e:
            return False, str(e)

    @http.route(
        "/verify/api", type="jsonrpc", auth="none", methods=["POST"], csrf=False
    )
    def verify_api_token(self):
        """
        Endpoint to verify if the provided API token is valid for the database.
        Also syncs printers if provided in the request.
        """
        valid, message = self._check_token_and_db()

        if not valid:
            return {"status": "error", "message": message}

        try:
            printers_data = request.httprequest.json.get("printers", [])

            if printers_data:

                api_token = request.httprequest.headers.get("Authorization")

                PrintEngineClient = request.env["print.engine.client"].sudo()
                client = PrintEngineClient.search(
                    [("print_engine_key", "=", api_token)], limit=1
                )

                if client:
                    sync_result = client.sync_printers_from_engine(printers_data)

                    return {
                        "status": "success",
                        "message": message,
                        "created": sync_result.get("created", 0),
                        "updated": sync_result.get("updated", 0),
                        "skipped": sync_result.get("skipped", 0),
                    }
                else:

                    return {
                        "status": "success",
                        "message": message,
                        "warning": "Print engine client not found for printer sync",
                    }
        except Exception as e:
            return {"status": "success", "message": message, "sync_error": str(e)}

        return {"status": "success", "message": message}

    @http.route(
        "/api/print_job", type="jsonrpc", auth="none", methods=["POST"], csrf=False
    )
    def print_jobs(self, **kwargs):
        """Fetch pending (draft) print jobs for the authenticated Print Engine Client."""

        api_token = request.httprequest.headers.get("Authorization")
        odoo_api_token = (
            request.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key")
        )

        if not odoo_api_token or not api_token:
            return []
        if api_token not in odoo_api_token:
            return []

        PrintJob = request.env["print.job"].sudo()

        jobs = PrintJob.search(
            [
                ("state", "=", "draft"),
                ("print_engine_key", "=", api_token),
            ],
            order="id asc",
        )

        if jobs:
            jobs.sudo().write(
                {
                    "state": "printing",
                }
            )
        result = jobs.read(["image_data", "printer_name", "print_type"])
        return result

    @http.route(
        "/api/print_job/update_status",
        type="jsonrpc",
        auth="none",
        csrf=False,
        methods=["POST"],
    )
    def update_multiple_statuses(self, **post):
        """
        Update the status of multiple print jobs in bulk or individually.

        """
        api_token = request.httprequest.headers.get("Authorization")
        odoo_api_token = (
            request.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key")
        )
        if api_token not in odoo_api_token:
            return {"status": "error", "message": "Invalid API token"}
        try:
            jobs = request.httprequest.json.get("jobs", [])
            if not jobs:
                return {"status": "error", "message": "No jobs provided"}

            states = set(job.get("state") for job in jobs)
            PrintJob = request.env["print.job"].sudo()

            if len(states) == 1:
                job_ids = [job.get("id") for job in jobs if job.get("id")]
                common_state = jobs[0].get("state")
                common_error = jobs[0].get("error_message", "")
                PrintJob.browse(job_ids).write(
                    {"state": common_state, "error_message": common_error}
                )
                return {
                    "status": "success",
                    "message": f"{len(job_ids)} jobs updated in bulk",
                    "job_ids": job_ids,
                }

            updated = []
            for job in jobs:
                job_id = job.get("id")
                state = job.get("state")
                error_message = job.get("error_message", "")
                if job_id and state:
                    PrintJob.browse(job_id).write(
                        {"state": state, "error_message": error_message}
                    )
                    updated.append(job_id)

            return {
                "status": "success",
                "message": f"{len(updated)} jobs updated individually",
                "job_ids": updated,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    @http.route(
        "/api/sync_printers", type="jsonrpc", auth="none", csrf=False, methods=["POST"]
    )
    def sync_printers(self, **post):
        """
        Receive discovered printers from the local Print Engine and sync them to Odoo.
        """
        api_token = request.httprequest.headers.get("Authorization")
        odoo_api_token = (
            request.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key")
        )

        if api_token not in odoo_api_token:
            return {"status": "error", "message": "Invalid API token"}

        try:
            printers_data = request.httprequest.json.get("printers", [])

            if not printers_data:
                return {"status": "warning", "message": "No printers provided"}

            PrintEngineClient = request.env["print.engine.client"].sudo()
            client = PrintEngineClient.search(
                [("print_engine_key", "=", api_token)], limit=1
            )

            if not client:
                return {"status": "error", "message": "Print engine client not found"}

            result = client.sync_printers_from_engine(printers_data)

            return result

        except Exception as e:
            return {"status": "error", "message": str(e)}
