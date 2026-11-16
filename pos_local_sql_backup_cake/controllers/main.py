# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

from odoo.addons.pos_custom_cake.controllers.main import PosCustomCakeController


class PosCustomCakeLocalBackupController(PosCustomCakeController):
    def _cake_create_response(self, order):
        data = order._prepare_pos_response()
        data["local_uuid"] = order.local_uuid or False
        return data

    @http.route()
    def create_order(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        local_uuid = str(payload.get("local_uuid") or "").strip()
        if local_uuid:
            existing = (
                request.env["pos.cake.order"]
                .sudo()
                .search([("local_uuid", "=", local_uuid)], limit=1)
            )
            if existing:
                return self._cake_create_response(existing)

        # Offline creates have no phone-upload session; ignore empty token.
        if local_uuid and not str(payload.get("upload_session_token") or "").strip():
            payload = dict(payload)
            payload.pop("upload_session_token", None)
            data = payload

        result = super().create_order(data=data, **kwargs)
        if local_uuid and result.get("id"):
            order = request.env["pos.cake.order"].sudo().browse(result["id"]).exists()
            if order and not order.local_uuid:
                order.local_uuid = local_uuid
            result["local_uuid"] = local_uuid
        return result

    @http.route()
    def search_orders(self, data=None, **kwargs):
        """Include product_id so offline load-from-cache can add the cake line."""
        rows = super().search_orders(data=data, **kwargs)
        ids = [row.get("id") for row in rows or [] if row.get("id")]
        if not ids:
            return rows
        orders = request.env["pos.cake.order"].sudo().browse(ids)
        by_id = {order.id: order for order in orders}
        enriched = []
        for row in rows:
            order = by_id.get(row.get("id"))
            next_row = dict(row)
            if order:
                next_row["product_id"] = order.product_id.id
                next_row["partner_id"] = order.partner_id.id
                next_row["price_before_tax"] = order.price_before_tax
                next_row["tax_amount"] = order.tax_amount
                next_row["cake_base_cost"] = order.cake_base_cost
                next_row["total_components_cost"] = order.total_components_cost
                next_row["sugar_paste"] = order.sugar_paste
                next_row["local_uuid"] = order.local_uuid or False
            enriched.append(next_row)
        return enriched
