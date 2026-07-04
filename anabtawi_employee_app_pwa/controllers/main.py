import json
import os

from odoo import http
from odoo.http import request


class AnabtawiEmployeeAppPWA(http.Controller):

    def _static_path(self, *parts):
        module_path = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(module_path, "static", "employee_app", *parts)

    @http.route("/employee-portal", type="http", auth="public", website=False)
    def employee_portal(self, **kwargs):
        with open(self._static_path("index.html"), "r", encoding="utf-8") as file:
            html = file.read()
        return request.make_response(
            html,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-cache"),
            ],
        )

    @http.route("/employee-portal/manifest.webmanifest", type="http", auth="public", website=False)
    def employee_manifest(self, **kwargs):
        with open(self._static_path("manifest.webmanifest"), "r", encoding="utf-8") as file:
            manifest = json.loads(file.read())
        return request.make_json_response(manifest)

    @http.route("/employee-portal/sw.js", type="http", auth="public", website=False)
    def employee_service_worker(self, **kwargs):
        with open(self._static_path("sw.js"), "r", encoding="utf-8") as file:
            body = file.read()
        return request.make_response(
            body,
            headers=[
                ("Content-Type", "application/javascript; charset=utf-8"),
                ("Service-Worker-Allowed", "/employee-portal"),
                ("Cache-Control", "no-cache"),
            ],
        )
