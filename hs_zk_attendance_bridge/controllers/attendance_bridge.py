# -*- coding: utf-8 -*-

import json

from odoo import http
from odoo.http import Response, request


class AttendanceBridgeController(http.Controller):
    @http.route(
        "/hs_zk_attendance_bridge/ping",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def ping(self, **kwargs):
        body = {"ok": True, "message": "Bridge endpoint is reachable."}
        return Response(json.dumps(body), status=200, mimetype="application/json")

    @http.route(
        "/hs_zk_attendance_bridge/push",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def push_attendance(self, **kwargs):
        payload = request.httprequest.get_json(silent=True) or {}
        token = payload.get("token") or request.httprequest.headers.get("X-Bridge-Token")
        device_identifier = payload.get("device_identifier")
        records = payload.get("records", [])

        if not token:
            return Response(
                json.dumps({"ok": False, "error": "Missing bridge token."}),
                status=400,
                mimetype="application/json",
            )

        device = request.env["biometric.device.bridge"].sudo().get_device_from_token(
            token, device_identifier=device_identifier
        )
        if not device:
            return Response(
                json.dumps({"ok": False, "error": "Invalid bridge token."}),
                status=403,
                mimetype="application/json",
            )

        try:
            results = device.import_bridge_records(
                records,
                source=payload.get("source") or "bridge_agent",
            )
        except Exception as exc:
            return Response(
                json.dumps({"ok": False, "error": str(exc)}),
                status=400,
                mimetype="application/json",
            )

        body = {"ok": True, "device": device.name, "results": results}
        return Response(json.dumps(body), status=200, mimetype="application/json")
