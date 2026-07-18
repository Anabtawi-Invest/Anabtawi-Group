from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request


def _json(data, status=200):
    return request.make_json_response(data, status=status)


def _error(code, message, status=400):
    return _json({"error": code, "message": message}, status=status)


def _payload():
    try:
        if request.httprequest.is_json:
            return request.get_json_data() or {}
    except Exception:
        pass
    return dict(request.params or {})


def _parse_bearer(value):
    parts = (value or "").strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


class AnabtawiSimpleAPI(http.Controller):

    def _authenticated_user(self):
        token = _parse_bearer(request.httprequest.headers.get("Authorization", ""))
        if not token:
            return None
        user = request.env["anabtawi.api.token"].authenticate_token(token)
        return user if user else None

    @http.route(
        "/api/v1/auth/login",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def api_login(self, **kwargs):
        """Login with db + username + password and return an access token."""
        payload = _payload()
        db_name = (payload.get("db") or payload.get("db_name") or "").strip()
        username = (payload.get("username") or payload.get("login") or "").strip()
        password = payload.get("password") or ""

        if not db_name or not username or not password:
            return _error(
                "invalid_request",
                "db, username and password are required.",
                status=400,
            )

        if request.db and db_name != request.db:
            return _error(
                "invalid_db",
                "Database name does not match the current database.",
                status=400,
            )

        wsgienv = {
            "interactive": False,
            "base_location": request.httprequest.url_root.rstrip("/"),
            "HTTP_HOST": request.httprequest.environ.get("HTTP_HOST", ""),
            "REMOTE_ADDR": request.httprequest.environ.get("REMOTE_ADDR", ""),
        }
        credential = {"type": "password", "login": username, "password": password}
        try:
            auth_info = request.env["res.users"].sudo().authenticate(credential, wsgienv)
        except AccessDenied:
            return _error("access_denied", "Invalid username or password.", status=401)

        user = request.env["res.users"].sudo().browse(auth_info["uid"])
        if not user or not user.active:
            return _error("access_denied", "Invalid username or password.", status=401)

        access_token = request.env["anabtawi.api.token"].issue_token(user)
        return _json({
            "status": "ok",
            "uid": user.id,
            "username": user.login,
            "db": request.db,
            "access_token": access_token,
            "token_type": "Bearer",
        })

    @http.route(
        "/api/v1/customers",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def api_customers(self, **kwargs):
        """Return all customers (res.partner with customer_rank > 0, or all companies/contacts)."""
        user = self._authenticated_user()
        if not user:
            return _error("unauthorized", "Invalid or missing Bearer token.", status=401)

        Partner = request.env["res.partner"].with_user(user)
        partners = Partner.search([("customer_rank", ">", 0)], order="name")

        data = []
        for partner in partners:
            data.append({
                "id": partner.id,
                "name": partner.name or "",
                "email": partner.email or "",
                "phone": partner.phone or "",
                "vat": partner.vat or "",
                "street": partner.street or "",
                "city": partner.city or "",
                "country": partner.country_id.name or "",
                "is_company": bool(partner.is_company),
                "customer_rank": partner.customer_rank,
            })

        return _json({
            "status": "ok",
            "count": len(data),
            "customers": data,
        })

    @http.route(
        "/api/v1/sale_orders",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def api_sale_orders(self, **kwargs):
        """Return all sale orders."""
        user = self._authenticated_user()
        if not user:
            return _error("unauthorized", "Invalid or missing Bearer token.", status=401)

        SaleOrder = request.env["sale.order"].with_user(user)
        orders = SaleOrder.search([], order="id desc")

        data = []
        for order in orders:
            data.append({
                "id": order.id,
                "name": order.name or "",
                "state": order.state or "",
                "date_order": fields_datetime(order.date_order),
                "partner_id": order.partner_id.id,
                "partner_name": order.partner_id.name or "",
                "amount_untaxed": order.amount_untaxed,
                "amount_tax": order.amount_tax,
                "amount_total": order.amount_total,
                "currency": order.currency_id.name or "",
                "company": order.company_id.name or "",
            })

        return _json({
            "status": "ok",
            "count": len(data),
            "sale_orders": data,
        })


def fields_datetime(value):
    if not value:
        return False
    return value.strftime("%Y-%m-%d %H:%M:%S") if hasattr(value, "strftime") else str(value)
