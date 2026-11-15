# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

from odoo.addons.pos_advance_order.controllers.main import PosAdvanceOrderController


class PosAdvanceOrderLocalBackupController(PosAdvanceOrderController):
    def _advance_create_response(self, order):
        return {
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "amount_total": order.amount_total,
            "pledge_amount": order.pledge_amount,
            "advance_amount": order.advance_amount,
            "amount_tendered": order.amount_tendered,
            "change_amount": order.change_amount,
            "amount_remaining": order.amount_remaining,
            "advance_pos_order_id": order.advance_pos_order_id.id,
            "local_uuid": order.local_uuid or False,
        }

    @http.route()
    def create_advance_order(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        local_uuid = str(payload.get("local_uuid") or "").strip()
        if local_uuid:
            existing = (
                request.env["pos.advance.order"]
                .sudo()
                .search([("local_uuid", "=", local_uuid)], limit=1)
            )
            if existing:
                return self._advance_create_response(existing)

        result = super().create_advance_order(data=data, **kwargs)
        if local_uuid and result.get("id"):
            order = request.env["pos.advance.order"].sudo().browse(result["id"]).exists()
            if order and not order.local_uuid:
                order.local_uuid = local_uuid
            result["local_uuid"] = local_uuid
        return result

    @http.route()
    def complete_advance_order(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        local_uuid = str(payload.get("local_uuid") or "").strip()
        if local_uuid and not payload.get("advance_order_id"):
            order = (
                request.env["pos.advance.order"]
                .sudo()
                .search([("local_uuid", "=", local_uuid)], limit=1)
            )
            if order:
                payload = dict(payload, advance_order_id=order.id)
                data = payload
        return super().complete_advance_order(data=data, **kwargs)
