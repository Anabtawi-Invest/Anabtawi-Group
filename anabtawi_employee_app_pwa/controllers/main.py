import mimetypes
import os

from odoo import http
from odoo.http import request

BASE_ROUTE = "/employee-portal"
IMMUTABLE_PREFIXES = ("_expo/", "assets/")


class AnabtawiEmployeeAppPWA(http.Controller):
    """Serves the Employee App web build at /employee-portal.

    The build is a single-page app (Expo Router, web output "single"). Real files
    (bundles, fonts, icons, manifest, service worker) are served as they are; any
    other path falls back to index.html so deep links such as
    /employee-portal/requests work after a refresh.
    """

    def _root(self):
        module_path = os.path.dirname(os.path.dirname(__file__))
        return os.path.realpath(os.path.join(module_path, "static", "employee_app"))

    def _safe_file(self, relative_path):
        root = self._root()
        full = os.path.realpath(os.path.join(root, relative_path))
        # Block path traversal: the resolved file must stay inside the build folder.
        if full != root and not full.startswith(root + os.sep):
            return None
        return full if os.path.isfile(full) else None

    def _respond(self, full_path, relative_path):
        content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"
        if relative_path.endswith(".webmanifest"):
            content_type = "application/manifest+json"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        with open(full_path, "rb") as handle:
            body = handle.read()
        headers = [("Content-Type", content_type)]
        if relative_path.startswith(IMMUTABLE_PREFIXES):
            # Build output is content-hashed, safe to cache for a year.
            headers.append(("Cache-Control", "public, max-age=31536000, immutable"))
        else:
            headers.append(("Cache-Control", "no-cache"))
        if relative_path == "sw.js":
            headers.append(("Service-Worker-Allowed", BASE_ROUTE + "/"))
        return request.make_response(body, headers=headers)

    @http.route(
        [BASE_ROUTE, BASE_ROUTE + "/", BASE_ROUTE + "/<path:subpath>"],
        type="http", auth="public", website=False, sitemap=False, csrf=False, methods=["GET", "HEAD"],
    )
    def employee_portal(self, subpath="", **kwargs):
        subpath = (subpath or "").strip("/")
        if subpath:
            full = self._safe_file(subpath)
            if full:
                return self._respond(full, subpath)
            # Missing asset (has a file extension): real 404, not the HTML shell.
            if "." in os.path.basename(subpath):
                return request.not_found()
        index = self._safe_file("index.html")
        if not index:
            return request.not_found()
        return self._respond(index, "index.html")
