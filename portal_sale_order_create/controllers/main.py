# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote

from odoo import _, fields, http
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
        """Pricelist from mapped van customer contact (property_product_pricelist)."""
        user = request.env.user.sudo()
        if "van_customer_id" in user._fields and user.van_customer_id:
            if hasattr(user, "_get_van_contact_pricelist"):
                return user._get_van_contact_pricelist()
            return user.van_customer_id.property_product_pricelist.sudo()
        return request.env["product.pricelist"]

    def _get_van_payment_journal(self):
        user = request.env.user.sudo()
        if "van_payment_journal_id" in user._fields and user.van_payment_journal_id:
            return user.van_payment_journal_id
        # Fallback used by direct sales module if present
        if (
            "salesperson_cash_journal_id" in user._fields
            and user.salesperson_cash_journal_id
        ):
            return user.salesperson_cash_journal_id
        return request.env["account.journal"]

    def _pay_invoice_amount(self, invoice, journal, amount=None):
        """Register a payment on posted invoice using the van journal.

        ``amount`` defaults to the residual (full pay). Pass a smaller amount for
        credit customers who only pay part now.
        """
        invoice.ensure_one()
        if not invoice or invoice.state != "posted":
            return
        if invoice.payment_state in ("paid", "in_payment"):
            return
        residual = invoice.amount_residual
        if residual <= 0:
            return
        pay_amount = residual if amount is None else float(amount)
        if pay_amount <= 0:
            return
        if pay_amount > residual + 1e-6:
            raise ValidationError(
                _(
                    "Payment amount %(amount)s cannot exceed the invoice residual %(residual)s."
                )
                % {"amount": pay_amount, "residual": residual}
            )
        if not journal:
            raise UserError(
                _(
                    "No payment journal is set on your user. "
                    "Ask an administrator to set Van Payment Journal."
                )
            )
        _logger.info(
            "portal_sale paying invoice=%s amount=%s residual=%s journal=%s",
            invoice.name,
            pay_amount,
            residual,
            journal.display_name,
        )
        payment_register = (
            request.env["account.payment.register"]
            .sudo()
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "journal_id": journal.id,
                    "amount": pay_amount,
                    "payment_date": fields.Date.context_today(invoice),
                }
            )
        )
        payment_register.action_create_payments()

    def _pay_invoice_fully(self, invoice, journal):
        """Register full payment on posted invoice using the van journal."""
        self._pay_invoice_amount(invoice, journal, amount=None)

    def _product_portal_price(self, product, pricelist=None):
        if pricelist:
            return pricelist._get_product_price(product, 1.0)
        return product.lst_price

    def _get_assigned_parent(self):
        """Contact assigned to this portal user; children are searchable customers."""
        user = request.env.user.sudo()
        if "van_customer_id" in user._fields and user.van_customer_id:
            return user.van_customer_id
        return user.partner_id

    def _normalize_sale_mode(self, sale_mode=None):
        mode = (sale_mode or "cash").strip().lower()
        if mode not in ("cash", "credit"):
            raise ValidationError(_("Invalid sale mode."))
        return mode

    def _is_allowed_cash_customer(self, partner):
        parent = self._get_assigned_parent()
        if not partner or not parent or not partner.active:
            return False
        if partner.parent_id.id != parent.id:
            return False
        return not bool(getattr(partner, "portal_allow_payment_term", False))

    def _is_allowed_credit_customer(self, partner):
        if not partner or not partner.active:
            return False
        if not bool(getattr(partner, "portal_allow_payment_term", False)):
            return False
        return partner.user_id.id == request.env.user.id

    def _is_allowed_portal_customer(self, partner, sale_mode="cash"):
        mode = self._normalize_sale_mode(sale_mode)
        if mode == "credit":
            return self._is_allowed_credit_customer(partner)
        return self._is_allowed_cash_customer(partner)

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
        return request.render(
            "portal_sale_order_create.portal_sale_create",
            {
                "page_name": "portal_sale_create",
                "sale_mode": "cash",
                "currency": request.env.company.currency_id,
                "draft_mode": self._is_draft_portal_user(),
            },
        )

    @http.route("/my/sales/credit/create", type="http", auth="user", website=True)
    def portal_sale_credit_create(self, **kwargs):
        self._ensure_sales_portal()
        return request.render(
            "portal_sale_order_create.portal_sale_create",
            {
                "page_name": "portal_sale_credit_create",
                "sale_mode": "credit",
                "currency": request.env.company.currency_id,
                "draft_mode": self._is_draft_portal_user(),
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

    @http.route(["/my/sales/api/partners", "/my/sales/api/partners/json"], type="jsonrpc", auth="user", website=True)
    def api_partners(self, term="", sale_mode="cash", **kwargs):
        self._ensure_sales_portal()
        return self._search_partners(term, sale_mode=sale_mode)

    @http.route("/my/sales/api/partners/http", type="http", auth="user", website=True, methods=["GET"], csrf=False)
    def api_partners_http(self, term="", sale_mode="cash", **kwargs):
        self._ensure_sales_portal()
        return request.make_json_response(self._search_partners(term, sale_mode=sale_mode))

    def _search_partners(self, term, sale_mode="cash"):
        """Cash: delivery contacts under van customer. Credit: salesperson = van."""
        term = (term or "").strip()
        if len(term) < 1:
            return []
        mode = self._normalize_sale_mode(sale_mode)

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

            domain = [("active", "=", True)]
            if mode == "credit":
                domain += [
                    ("user_id", "=", request.env.user.id),
                    ("portal_allow_payment_term", "=", True),
                ]
            else:
                parent = self._get_assigned_parent()
                if not parent:
                    return []
                domain += [
                    ("parent_id", "=", parent.id),
                    ("portal_allow_payment_term", "=", False),
                ]
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

    @http.route("/my/sales/api/cash_customers/create", type="jsonrpc", auth="user", website=True)
    def api_create_cash_customer(self, name="", phone="", email="", **kwargs):
        self._ensure_sales_portal()
        return self._create_cash_customer(name, phone, email)

    @http.route(
        "/my/sales/api/cash_customers/create/http",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def api_create_cash_customer_http(self, **kwargs):
        self._ensure_sales_portal()
        payload = request.get_json_data() if request.httprequest.is_json else kwargs
        return request.make_json_response(
            self._create_cash_customer(
                payload.get("name", ""),
                payload.get("phone", ""),
                payload.get("email", ""),
            )
        )

    def _create_cash_customer(self, name, phone, email):
        name = (name or "").strip()
        phone = (phone or "").strip()
        email = (email or "").strip()
        if not name:
            raise ValidationError(_("Customer name is required."))
        parent = self._get_assigned_parent()
        if not parent:
            raise UserError(
                _("No van customer is assigned on your user. Contact an administrator.")
            )
        user = request.env.user.sudo()
        company = user.company_id or parent.company_id or request.env.company
        vals = {
            "name": name,
            "phone": phone or False,
            "email": email or False,
            "parent_id": parent.id,
            "type": "delivery",
            "customer_rank": 1,
            "is_company": False,
            "company_id": company.id if company else False,
            "portal_allow_payment_term": False,
            "property_payment_term_id": False,
        }
        Partner = request.env["res.partner"].sudo()
        partner = Partner.with_company(company).create(vals) if company else Partner.create(vals)
        return {
            "id": partner.id,
            "name": partner.display_name or partner.name,
            "phone": partner.phone or "",
            "email": partner.email or "",
            "portal_allow_payment_term": False,
            "default_payment_term_id": False,
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
        sale_mode="cash",
        **kwargs,
    ):
        self._ensure_sales_portal()
        mode = self._normalize_sale_mode(sale_mode)
        lines = lines or []
        if not lines:
            raise ValidationError(_("Please add at least one product."))

        if not partner_id:
            raise ValidationError(_("Please select a customer."))
        partner = request.env["res.partner"].sudo().browse(int(partner_id)).exists()
        if not partner or not self._is_allowed_portal_customer(partner, sale_mode=mode):
            raise ValidationError(
                _("Customer not found among your allowed %(mode)s customers.")
                % {"mode": mode}
            )

        if mode == "credit":
            payment_term = self._resolve_payment_term(partner, payment_term_id)
        else:
            payment_term = self._get_immediate_payment_term()
            if not payment_term:
                raise ValidationError(
                    _("No payment terms found. Please configure Immediate Payment.")
                )

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
        # Invoices stay unpaid; backend marks them paid.
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
