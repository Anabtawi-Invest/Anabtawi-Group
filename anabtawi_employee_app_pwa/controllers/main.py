# -*- coding: utf-8 -*-

import os
from odoo import http
from odoo.http import request


class AnabtawiEmployeeAppPWA(http.Controller):

    @http.route(
        "/employee-portal",
        type="http",
        auth="public",
        website=False,
        csrf=False,
        sitemap=False,
    )
    def employee_portal(self, **kwargs):
        module_path = os.path.dirname(os.path.dirname(__file__))
        index_path = os.path.join(
            module_path,
            "static",
            "employee_portal",
            "index.html",
        )

        if not os.path.exists(index_path):
            return request.not_found()

        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        return request.make_response(
            html,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-cache"),
            ],
        )
