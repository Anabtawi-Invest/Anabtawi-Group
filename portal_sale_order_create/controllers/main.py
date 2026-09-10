# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager

_logger = logging.getLogger(__name__)

GROUP_XMLID = "portal_sale_order_create.group_sales_portal"


class PortalSaleOrderCreate(http.Controller):

    def _ensure_sales_portal(self):
        if request.env.user._is_public() or not request.env.user.has_group(GROUP_XMLID):
            raise AccessError(_("You do not have access to Sales Portal."))

    def _get_my_order(self, order_id):
        order = request.env["sale.order"].sudo().browse(order_id).exists()
        if not order or order.create_uid.id != request.env.user.id:
            raise AccessError(_("Order not found or access denied."))
        return order

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @http.route("/my/sales/create", type="http", auth="user", website=True)
    def portal_sale_create(self, **kwargs):
        self._ensure_sales_portal()
        return request.render(
            "portal_sale_order_create.portal_sale_create",
            {
                "page_name": "portal_sale_create",
                "currency": request.env.company.currency_id,
            },
        )

    @http.route(["/my/sales/orders", "/my/sales/orders/page/<int:page>"], type="http", auth="user", website=True)
    def portal_sale_orders(self, page=1, **kwargs):
        self._ensure_sales_portal()
        SaleOrder = request.env["sale.order"].sudo()
        domain = [("create_uid", "=", request.env.user.id)]
        total = SaleOrder.search_count(domain)
        pager = portal_pager(
            url="/my/sales/orders",
            total=total,
            page=page,
            step=20,
            url_args={},
        )
        orders = SaleOrder.search(domain, order="date_order desc, id desc", limit=20, offset=pager["offset"])
        return request.render(
            "portal_sale_order_create.portal_sale_orders",
            {
                "page_name": "portal_sale_orders",
                "orders": orders,
                "pager": pager,
            },
        )

    @http.route("/my/sales/orders/<int:order_id>", type="http", auth="user", website=True)
    def portal_sale_order_detail(self, order_id, **kwargs):
        self._ensure_sales_portal()
        order = self._get_my_order(order_id)
        invoice = self._main_invoice(order)
        return request.render(
            "portal_sale_order_create.portal_sale_order_detail",
            {
                "page_name": "portal_sale_order_detail",
                "order": order,
                "invoice": invoice,
                "whatsapp_url": self._whatsapp_url(invoice) if invoice else False,
                "print_url": self._invoice_print_url(invoice) if invoice else False,
            },
        )

    # ------------------------------------------------------------------
    # JSON API
    # ------------------------------------------------------------------

    @http.route("/my/sales/api/partners", type="jsonrpc", auth="user", website=True)
    def api_partners(self, term="", **kwargs):
        self._ensure_sales_portal()
        term = (term or "").strip()
        if len(term) < 1:
            return []

        Partner = request.env["res.partner"].sudo()
        digits = re.sub(r"\D", "", term)

        # Match name / phone / mobile / email as the user types
        or_domain = [
            ("name", "ilike", term),
            ("display_name", "ilike", term),
            ("phone", "ilike", term),
            ("mobile", "ilike", term),
            ("email", "ilike", term),
        ]
        # Extra digit-only match helps when phone is stored with spaces/+/-
        if len(digits) >= 2:
            or_domain += [
                ("phone", "ilike", digits),
                ("mobile", "ilike", digits),
            ]

        domain = ["&", ("active", "=", True)]
        # Build (... OR ... OR ...)
        for _ in range(len(or_domain) - 1):
            domain.append("|")
        domain.extend(or_domain)

        partners = Partner.search(domain, limit=25, order="name, id")
        return [
            {
                "id": p.id,
                "name": p.display_name or p.name,
                "phone": p.phone or p.mobile or "",
                "email": p.email or "",
            }
            for p in partners
        ]

    @http.route("/my/sales/api/partner/create", type="jsonrpc", auth="user", website=True)
    def api_partner_create(self, name="", phone="", email="", **kwargs):
        self._ensure_sales_portal()
        name = (name or "").strip()
        if not name:
            raise ValidationError(_("Customer name is required."))
        partner = request.env["res.partner"].sudo().create(
            {
                "name": name,
                "phone": (phone or "").strip() or False,
                "email": (email or "").strip() or False,
                "customer_rank": 1,
            }
        )
        return {
            "id": partner.id,
            "name": partner.name,
            "phone": partner.phone or "",
            "email": partner.email or "",
        }

    @http.route("/my/sales/api/products", type="jsonrpc", auth="user", website=True)
    def api_products(self, term="", offset=0, limit=60, **kwargs):
        self._ensure_sales_portal()
        term = (term or "").strip()
        try:
            offset = max(int(offset or 0), 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            limit = min(max(int(limit or 60), 1), 200)
        except (TypeError, ValueError):
            limit = 60

        domain = [("sale_ok", "=", True), ("active", "=", True)]
        if term:
            domain += [
                "|",
                "|",
                ("name", "ilike", term),
                ("default_code", "ilike", term),
                ("barcode", "ilike", term),
            ]
        Product = request.env["product.product"].sudo()
        total = Product.search_count(domain)
        products = Product.search(domain, limit=limit, offset=offset, order="default_code, name, id")
        company = request.env.company
        currency = company.currency_id
        result = []
        for product in products:
            price = product.lst_price
            result.append(
                {
                    "id": product.id,
                    "name": product.display_name,
                    "price": price,
                    "price_display": f"{price:.2f} {currency.symbol}",
                    "image_url": f"/web/image/product.product/{product.id}/image_128",
                    "uom": product.uom_id.name,
                }
            )
        return {
            "products": result,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(result) < total,
        }

    @http.route("/my/sales/api/confirm", type="jsonrpc", auth="user", website=True)
    def api_confirm(self, partner_id=None, lines=None, **kwargs):
        self._ensure_sales_portal()
        if not partner_id:
            raise ValidationError(_("Please select a customer."))
        lines = lines or []
        if not lines:
            raise ValidationError(_("Please add at least one product."))

        partner = request.env["res.partner"].sudo().browse(int(partner_id)).exists()
        if not partner:
            raise ValidationError(_("Customer not found."))

        order_lines = []
        for line in lines:
            product_id = int(line.get("product_id") or 0)
            qty = float(line.get("qty") or 0)
            if not product_id or qty <= 0:
                continue
            product = request.env["product.product"].sudo().browse(product_id).exists()
            if not product or not product.sale_ok:
                raise ValidationError(_("Invalid product selected."))
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "product_uom_qty": qty,
                    },
                )
            )
        if not order_lines:
            raise ValidationError(_("Please add at least one product with quantity."))

        order = (
            request.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": partner.id,
                    "user_id": request.env.user.id,
                    "order_line": order_lines,
                }
            )
        )
        order.action_confirm()
        invoices = order._create_invoices()
        invoices.action_post()
        invoice = invoices[:1]
        return {
            "order_id": order.id,
            "order_name": order.name,
            "invoice_id": invoice.id if invoice else False,
            "invoice_name": invoice.name if invoice else False,
            "redirect_url": f"/my/sales/orders/{order.id}",
        }

    @http.route("/my/sales/api/cancel", type="jsonrpc", auth="user", website=True)
    def api_cancel(self, order_id=None, **kwargs):
        self._ensure_sales_portal()
        order = self._get_my_order(int(order_id))
        if order.state == "cancel":
            return {"ok": True, "message": _("Order is already cancelled.")}
        self._cancel_order_with_invoices(order)
        return {"ok": True, "message": _("Order cancelled successfully.")}

    @http.route("/my/sales/api/send_email", type="jsonrpc", auth="user", website=True)
    def api_send_email(self, order_id=None, **kwargs):
        self._ensure_sales_portal()
        order = self._get_my_order(int(order_id))
        invoice = order.invoice_ids.filtered(
            lambda m: m.state == "posted" and m.move_type in ("out_invoice", "out_receipt")
        )[:1]
        if not invoice:
            raise UserError(_("No posted invoice found for this order."))
        if not invoice.partner_id.email:
            raise UserError(_("Customer has no email address."))
        request.env["account.move.send"].sudo()._generate_and_send_invoices(
            invoice,
            sending_methods=["email"],
        )
        return {"ok": True, "message": _("Invoice sent by email.")}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cancel_order_with_invoices(self, order):
        invoices = order.invoice_ids.filtered(lambda m: m.state != "cancel")
        posted = invoices.filtered(
            lambda m: m.state == "posted" and m.move_type in ("out_invoice", "out_receipt")
        )
        draft = invoices.filtered(lambda m: m.state == "draft")
        if posted:
            posted._reverse_moves(
                default_values_list=[{"ref": _("Cancel %s", move.name)} for move in posted],
                cancel=True,
            )
        if draft:
            draft.button_cancel()
        if order.locked:
            order.action_unlock()
        if order.state != "cancel":
            order.action_cancel()

    def _invoice_print_url(self, invoice):
        if not invoice:
            return False
        invoice._portal_ensure_token()
        return invoice.get_portal_url(report_type="pdf", download=True)

    def _whatsapp_url(self, invoice):
        if not invoice:
            return False
        partner = invoice.partner_id
        phone = partner.mobile or partner.phone or ""
        digits = re.sub(r"\D", "", phone)
        if not digits:
            return False
        invoice._portal_ensure_token()
        link = request.httprequest.host_url.rstrip("/") + invoice.get_portal_url(report_type="pdf")
        message = _(
            "Hello %(name)s, your invoice %(invoice)s: %(link)s",
            name=partner.name,
            invoice=invoice.name,
            link=link,
        )
        return f"https://wa.me/{digits}?text={quote(message)}"

    def _main_invoice(self, order):
        return order.invoice_ids.filtered(
            lambda m: m.state != "cancel" and m.move_type in ("out_invoice", "out_receipt")
        )[:1]
