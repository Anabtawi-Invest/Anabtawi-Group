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
GROUP_DRAFT_XMLID = "portal_sale_order_create.group_sales_portal_draft"


class PortalSaleOrderCreate(http.Controller):

    def _ensure_sales_portal(self):
        if request.env.user._is_public() or not request.env.user.has_group(GROUP_XMLID):
            raise AccessError(_("You do not have access to Sales Portal."))

    def _is_draft_portal_user(self):
        return request.env.user.has_group(GROUP_DRAFT_XMLID)

    def _get_my_order(self, order_id):
        order = request.env["sale.order"].sudo().browse(order_id).exists()
        if not order or order.create_uid.id != request.env.user.id:
            raise AccessError(_("Order not found or access denied."))
        return order

    def _get_van_stock_location(self):
        """Van Stock location for the logged-in portal user (not transit)."""
        user = request.env.user.sudo()
        if "van_warehouse_id" in user._fields and user.van_warehouse_id:
            stock = user.van_warehouse_id.lot_stock_id
            if stock and stock.active:
                return stock
        if "portal.transfer.location.map" in request.env:
            mapping = (
                request.env["portal.transfer.location.map"]
                .sudo()
                .search(
                    [("user_id", "=", user.id), ("active", "=", True)],
                    limit=1,
                )
            )
            if mapping.stock_location_id and mapping.stock_location_id.active:
                return mapping.stock_location_id
        return request.env["stock.location"]

    def _get_van_warehouse(self):
        user = request.env.user.sudo()
        if "van_warehouse_id" in user._fields and user.van_warehouse_id:
            return user.van_warehouse_id
        return request.env["stock.warehouse"]

    def _get_van_pricelist(self):
        user = request.env.user.sudo()
        if "van_pricelist_id" in user._fields and user.van_pricelist_id:
            return user.van_pricelist_id
        return request.env["product.pricelist"]

    def _product_portal_price(self, product, pricelist=None):
        if pricelist:
            return pricelist._get_product_price(product, 1.0)
        return product.lst_price

    def _get_van_customer(self):
        """Mapped van customer exactly (sale partner + address parent)."""
        user = request.env.user.sudo()
        if "van_customer_id" in user._fields and user.van_customer_id:
            mapped = user.van_customer_id
            _logger.info(
                "portal_sale van_customer user=%s mapped_id=%s mapped_name=%r "
                "mapped_is_company=%s commercial_id=%s",
                user.id,
                mapped.id,
                mapped.display_name,
                mapped.is_company,
                mapped.commercial_partner_id.id,
            )
            return mapped
        return request.env["res.partner"]

    def _serialize_address(self, partner):
        return {
            "id": partner.id,
            "name": partner.name or "",
            "street": partner.street or "",
            "city": partner.city or "",
            "phone": partner.phone or "",
            "display": self._address_display(partner),
        }

    def _address_display(self, partner):
        parts = [
            partner.name or "",
            partner.street or "",
            partner.city or "",
            partner.phone or "",
        ]
        return " — ".join(p for p in parts if p)

    def _get_van_delivery_addresses(self, customer):
        if not customer:
            return request.env["res.partner"]
        # Addresses under the mapped van customer (and any wrongly stored under commercial)
        parents = customer | customer.commercial_partner_id
        addresses = (
            request.env["res.partner"]
            .sudo()
            .search(
                [
                    ("parent_id", "in", parents.ids),
                    ("type", "in", ("delivery", "other")),
                    ("active", "=", True),
                ],
                order="name, id",
            )
        )
        _logger.info(
            "portal_sale list addresses customer_id=%s parents=%s count=%s ids=%s",
            customer.id,
            parents.ids,
            len(addresses),
            addresses.ids,
        )
        return addresses

    def _resolve_van_shipping_address(self, customer, address_id=None, address=None):
        Partner = request.env["res.partner"].sudo()
        # Always nest under the mapped van customer the user configured
        parent = customer
        allowed_parents = customer | customer.commercial_partner_id
        _logger.info(
            "portal_sale resolve address parent_id=%s parent_name=%r is_company=%s "
            "address_id=%s address_payload=%r",
            parent.id,
            parent.display_name,
            parent.is_company,
            address_id,
            address,
        )
        if address_id:
            shipping = Partner.browse(int(address_id)).exists()
            _logger.info(
                "portal_sale existing address id=%s parent_id=%s type=%s active=%s",
                shipping.id if shipping else None,
                shipping.parent_id.id if shipping else None,
                shipping.type if shipping else None,
                shipping.active if shipping else None,
            )
            if (
                not shipping
                or shipping.parent_id.id not in allowed_parents.ids
                or shipping.type not in ("delivery", "other")
            ):
                raise ValidationError(_("Invalid delivery address selected."))
            # If it was stored under commercial company, re-parent onto mapped customer
            if shipping.parent_id.id != parent.id:
                _logger.warning(
                    "portal_sale re-parenting address %s from %s to mapped customer %s",
                    shipping.id,
                    shipping.parent_id.id,
                    parent.id,
                )
                shipping.write({"parent_id": parent.id})
            return shipping

        address = address or {}
        name = (address.get("name") or "").strip()
        street = (address.get("street") or "").strip()
        city = (address.get("city") or "").strip()
        phone = (address.get("phone") or "").strip()
        if not name:
            raise ValidationError(_("Please enter the place / person name."))
        if not street:
            raise ValidationError(_("Please enter the street."))
        if not city:
            raise ValidationError(_("Please enter the city."))

        vals = {
            "name": name,
            "street": street,
            "city": city,
            "phone": phone or False,
            "type": "delivery",
            "parent_id": parent.id,
            "is_company": False,
        }
        if parent.company_id:
            vals["company_id"] = parent.company_id.id
        else:
            vals["company_id"] = False

        _logger.info("portal_sale creating delivery address vals=%r", vals)
        shipping = Partner.create(vals)
        shipping.invalidate_recordset()
        parent.invalidate_recordset(["child_ids"])
        _logger.info(
            "portal_sale created address id=%s name=%r parent_id=%s type=%s "
            "company_id=%s child_ids_on_parent=%s",
            shipping.id,
            shipping.name,
            shipping.parent_id.id,
            shipping.type,
            shipping.company_id.id,
            parent.child_ids.ids,
        )
        if shipping.parent_id.id != parent.id:
            _logger.error(
                "portal_sale address parent mismatch after create: expected=%s got=%s — forcing parent",
                parent.id,
                shipping.parent_id.id,
            )
            shipping.write({"parent_id": parent.id})
        return shipping

    def _available_qty_by_product(self, location, product_ids=None):
        """Map product_id -> available qty (on hand - reserved) in location tree."""
        if not location:
            return {}
        domain = [
            ("location_id", "child_of", location.id),
            ("product_id.active", "=", True),
        ]
        if product_ids is not None:
            if not product_ids:
                return {}
            domain.append(("product_id", "in", list(product_ids)))
        groups = (
            request.env["stock.quant"]
            .sudo()
            .read_group(
                domain,
                ["product_id", "quantity:sum", "reserved_quantity:sum"],
                ["product_id"],
                lazy=False,
            )
        )
        result = {}
        for group in groups:
            if not group.get("product_id"):
                continue
            product_id = group["product_id"][0]
            available = (group.get("quantity") or 0.0) - (group.get("reserved_quantity") or 0.0)
            if available > 0:
                result[product_id] = available
        return result

    @http.route("/my/sales/create", type="http", auth="user", website=True)
    def portal_sale_create(self, **kwargs):
        self._ensure_sales_portal()
        van_customer = self._get_van_customer()
        addresses = self._get_van_delivery_addresses(van_customer) if van_customer else []
        return request.render(
            "portal_sale_order_create.portal_sale_create",
            {
                "page_name": "portal_sale_create",
                "currency": request.env.company.currency_id,
                "draft_mode": self._is_draft_portal_user(),
                "van_customer": van_customer,
                "van_addresses": addresses,
            },
        )

    @http.route("/my/sales/api/addresses", type="jsonrpc", auth="user", website=True)
    def api_addresses(self, **kwargs):
        self._ensure_sales_portal()
        van_customer = self._get_van_customer()
        if not van_customer:
            return {"customer": False, "addresses": []}
        addresses = self._get_van_delivery_addresses(van_customer)
        return {
            "customer": {
                "id": van_customer.id,
                "name": van_customer.display_name or van_customer.name,
                "portal_allow_payment_term": bool(van_customer.portal_allow_payment_term),
                "default_payment_term_id": van_customer.property_payment_term_id.id or False,
            },
            "addresses": [self._serialize_address(a) for a in addresses],
        }

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

    @http.route(["/my/sales/api/partners", "/my/sales/api/partners/json"], type="jsonrpc", auth="user", website=True)
    def api_partners(self, term="", **kwargs):
        self._ensure_sales_portal()
        return self._search_partners(term)

    @http.route("/my/sales/api/partners/http", type="http", auth="user", website=True, methods=["GET"], csrf=False)
    def api_partners_http(self, term="", **kwargs):
        self._ensure_sales_portal()
        return request.make_json_response(self._search_partners(term))

    def _search_partners(self, term):
        """Search customers by name, phone, or email only."""
        term = (term or "").strip()
        if len(term) < 1:
            return []

        try:
            Partner = request.env["res.partner"].sudo()
            digits = re.sub(r"\D", "", term)
            or_clauses = [
                ("name", "ilike", term),
                ("phone", "ilike", term),
                ("email", "ilike", term),
            ]
            if len(digits) >= 2:
                or_clauses.append(("phone", "ilike", digits))

            domain = ["&", ("active", "=", True)]
            for _ in range(len(or_clauses) - 1):
                domain.append("|")
            domain.extend(or_clauses)

            partners = Partner.search(domain, limit=25, order="name, id")
            return [
                {
                    "id": p.id,
                    "name": p.display_name or p.name,
                    "phone": p.phone or "",
                    "email": p.email or "",
                    "portal_allow_payment_term": bool(p.portal_allow_payment_term),
                    "default_payment_term_id": p.property_payment_term_id.id or False,
                }
                for p in partners
            ]
        except Exception:
            _logger.exception("portal_sale_order_create: partner search failed for term=%r", term)
            return []

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

        van_location = self._get_van_stock_location()
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
        available_map = {}
        if van_location:
            available_map = self._available_qty_by_product(van_location)
            if not available_map:
                return {
                    "products": [],
                    "total": 0,
                    "offset": offset,
                    "limit": limit,
                    "has_more": False,
                    "van_stock_location": van_location.complete_name or van_location.name,
                }
            domain.append(("id", "in", list(available_map.keys())))

        total = Product.search_count(domain)
        products = Product.search(
            domain, limit=limit, offset=offset, order="default_code, name, id"
        )
        pricelist = self._get_van_pricelist()
        currency = (pricelist.currency_id if pricelist else request.env.company.currency_id)
        result = []
        for product in products:
            price = self._product_portal_price(product, pricelist)
            qty_available = available_map.get(product.id) if van_location else False
            result.append(
                {
                    "id": product.id,
                    "name": product.display_name,
                    "price": price,
                    "price_display": f"{price:.2f} {currency.symbol}",
                    "image_url": f"/web/image/product.product/{product.id}/image_128",
                    "uom": product.uom_id.name,
                    "qty_available": qty_available,
                    "qty_available_display": (
                        f"{qty_available:g} {product.uom_id.name}"
                        if qty_available is not False
                        else False
                    ),
                }
            )
        return {
            "products": result,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(result) < total,
            "van_stock_location": (
                van_location.complete_name or van_location.name if van_location else False
            ),
        }

    @http.route("/my/sales/api/payment_terms", type="jsonrpc", auth="user", website=True)
    def api_payment_terms(self, **kwargs):
        self._ensure_sales_portal()
        return self._get_payment_terms()

    @http.route(
        "/my/sales/api/payment_terms/http",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def api_payment_terms_http(self, **kwargs):
        self._ensure_sales_portal()
        return request.make_json_response(self._get_payment_terms())

    def _get_payment_terms(self):
        company = request.env.company
        terms = (
            request.env["account.payment.term"]
            .sudo()
            .search(
                [
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", company.id),
                ],
                order="name, id",
            )
        )
        return [{"id": term.id, "name": term.display_name or term.name} for term in terms]

    def _validate_sale_deliveries(self, order):
        """Validate outgoing deliveries so van stock on-hand decreases immediately."""
        pickings = order.picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
            and p.picking_type_id.code == "outgoing"
        )
        _logger.info(
            "portal_sale validate deliveries order=%s warehouse=%s pickings=%s",
            order.name,
            order.warehouse_id.display_name,
            pickings.mapped("name"),
        )
        for picking in pickings:
            if picking.state == "draft":
                picking.action_confirm()
            if picking.state in ("confirmed", "assigned", "waiting"):
                picking.action_assign()
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            ):
                if move.product_uom_qty and not move.quantity:
                    move.quantity = move.product_uom_qty
            picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            ).picked = True
            result = picking.with_context(
                skip_backorder=True,
                skip_sms=True,
                skip_sanity_check=True,
            ).button_validate()
            if isinstance(result, dict):
                picking.with_context(
                    skip_backorder=True,
                    cancel_backorder=True,
                    skip_sms=True,
                    skip_sanity_check=True,
                )._action_done()
            _logger.info(
                "portal_sale delivery %s state=%s src=%s",
                picking.name,
                picking.state,
                picking.location_id.complete_name,
            )

    def _get_immediate_payment_term(self):
        term = request.env.ref(
            "account.account_payment_term_immediate",
            raise_if_not_found=False,
        )
        if term:
            return term.sudo()
        company = request.env.company
        return (
            request.env["account.payment.term"]
            .sudo()
            .search(
                [
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", company.id),
                ],
                order="id asc",
                limit=1,
            )
        )

    def _resolve_payment_term(self, partner, payment_term_id=None):
        """Selected term, else partner default, else Immediate Payment."""
        Term = request.env["account.payment.term"].sudo()
        payment_term = Term
        if partner.portal_allow_payment_term:
            if not payment_term_id:
                raise ValidationError(_("Please select payment terms."))
            payment_term = Term.browse(int(payment_term_id)).exists()
            if not payment_term:
                raise ValidationError(_("Invalid payment terms selected."))
            if payment_term.company_id and payment_term.company_id != request.env.company:
                raise ValidationError(_("Invalid payment terms selected."))
            return payment_term

        if payment_term_id:
            payment_term = Term.browse(int(payment_term_id)).exists()
        if not payment_term and partner.property_payment_term_id:
            payment_term = partner.property_payment_term_id
        if not payment_term:
            payment_term = self._get_immediate_payment_term()
        if not payment_term:
            raise ValidationError(
                _("No payment terms found. Please configure Immediate Payment.")
            )
        return payment_term

    @http.route("/my/sales/api/confirm", type="jsonrpc", auth="user", website=True)
    def api_confirm(
        self,
        partner_id=None,
        lines=None,
        payment_term_id=None,
        address_id=None,
        address=None,
        **kwargs,
    ):
        self._ensure_sales_portal()
        lines = lines or []
        if not lines:
            raise ValidationError(_("Please add at least one product."))

        van_customer = self._get_van_customer()
        shipping = request.env["res.partner"]
        if van_customer:
            partner = van_customer
            shipping = self._resolve_van_shipping_address(van_customer, address_id, address)
        else:
            if not partner_id:
                raise ValidationError(_("Please select a customer."))
            partner = request.env["res.partner"].sudo().browse(int(partner_id)).exists()
            if not partner:
                raise ValidationError(_("Customer not found."))

        payment_term = self._resolve_payment_term(partner, payment_term_id)

        van_location = self._get_van_stock_location()
        van_warehouse = self._get_van_warehouse()
        available_map = (
            self._available_qty_by_product(van_location) if van_location else {}
        )

        order_lines = []
        for line in lines:
            product_id = int(line.get("product_id") or 0)
            qty = float(line.get("qty") or 0)
            if not product_id or qty <= 0:
                continue
            product = request.env["product.product"].sudo().browse(product_id).exists()
            if not product or not product.sale_ok:
                raise ValidationError(_("Invalid product selected."))
            if van_location:
                available = available_map.get(product.id, 0.0)
                if available <= 0:
                    raise ValidationError(
                        _("Product %(product)s is not available in your van stock.")
                        % {"product": product.display_name}
                    )
                if qty > available:
                    raise ValidationError(
                        _(
                            "Not enough stock for %(product)s. "
                            "Available: %(available)s %(uom)s, requested: %(qty)s."
                        )
                        % {
                            "product": product.display_name,
                            "available": available,
                            "uom": product.uom_id.name,
                            "qty": qty,
                        }
                    )
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

        van_pricelist = self._get_van_pricelist()
        order_vals = {
            "partner_id": partner.id,
            "user_id": request.env.user.id,
            "payment_term_id": payment_term.id,
            "order_line": order_lines,
        }
        if shipping:
            order_vals["partner_shipping_id"] = shipping.id
        if van_warehouse:
            order_vals["warehouse_id"] = van_warehouse.id
        if van_pricelist:
            order_vals["pricelist_id"] = van_pricelist.id

        order = request.env["sale.order"].sudo().create(order_vals)
        # Ensure van warehouse sticks (compute may reset it on create)
        if van_warehouse and order.warehouse_id != van_warehouse:
            order.warehouse_id = van_warehouse.id
            _logger.info(
                "portal_sale forced warehouse_id=%s on order %s",
                van_warehouse.id,
                order.name,
            )

        if self._is_draft_portal_user():
            return {
                "order_id": order.id,
                "order_name": order.name,
                "invoice_id": False,
                "invoice_name": False,
                "draft": True,
                "redirect_url": f"/my/sales/orders/{order.id}",
            }

        order.action_confirm()
        self._validate_sale_deliveries(order)
        invoices = order._create_invoices()
        invoices.action_post()
        invoice = invoices[:1]
        return {
            "order_id": order.id,
            "order_name": order.name,
            "invoice_id": invoice.id if invoice else False,
            "invoice_name": invoice.name if invoice else False,
            "draft": False,
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
        phone = partner.phone or ""
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
