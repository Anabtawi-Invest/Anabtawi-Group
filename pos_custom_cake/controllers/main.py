# -*- coding: utf-8 -*-
from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request


class PosCustomCakeController(http.Controller):

    @http.route("/pos/custom_cake/get_config", type="jsonrpc", auth="user")
    def get_config(self, **kwargs):
        return request.env["pos.cake.order"].get_pos_config_data()

    @http.route("/pos/custom_cake/compute_prices", type="jsonrpc", auth="user")
    def compute_prices(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        return request.env["pos.cake.order"].compute_preview_prices(payload)

    @http.route("/pos/custom_cake/create_order", type="jsonrpc", auth="user")
    def create_order(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        return request.env["pos.cake.order"].create_from_pos(payload)

    @http.route("/pos/custom_cake/search_orders", type="jsonrpc", auth="user")
    def search_orders(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        query = payload.get("query") or ""
        limit = int(payload.get("limit") or 50)
        return request.env["pos.cake.order"].search_for_pos(query=query, limit=limit)

    @http.route("/pos/custom_cake/get_order", type="jsonrpc", auth="user")
    def get_order(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        order_id = int(payload.get("order_id") or 0)
        order = request.env["pos.cake.order"].sudo().browse(order_id).exists()
        if not order:
            raise ValidationError(_("Cake order not found."))
        if order.state != "waiting_payment":
            raise ValidationError(_("This cake order is not waiting for payment."))
        return order._prepare_pos_response()
