# -*- coding: utf-8 -*-
import logging
import re

from odoo import _, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager

_logger = logging.getLogger(__name__)

GROUP_XMLID = "approvals_create_customer.group_portal_customer_request"
CATEGORY_XMLID = "approvals_create_customer.approval_category_data_create_customer"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PortalCustomerRequest(http.Controller):

    def _ensure_access(self):
        if request.env.user._is_public() or not request.env.user.has_group(GROUP_XMLID):
            raise AccessError(_("You do not have access to Customer Request Portal."))

    def _get_category(self):
        Category = request.env["approval.category"].sudo()
        company = request.env.company
        category = Category.search(
            [
                ("approval_type", "=", "create_customer"),
                ("company_id", "=", company.id),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not category:
            category = request.env.ref(CATEGORY_XMLID, raise_if_not_found=False)
        if not category or not category.exists() or not category.active:
            raise UserError(
                _("Create Customer approval category is not configured. Please contact an administrator.")
            )
        # Portal create-customer must NOT use approval_contact mandatory VAT/attachment rules
        if "x_create_contact_on_approve" in category._fields and category.x_create_contact_on_approve:
            category.x_create_contact_on_approve = False
        return category

    def _get_my_request(self, request_id):
        approval = request.env["approval.request"].sudo().browse(int(request_id)).exists()
        if (
            not approval
            or approval.approval_type != "create_customer"
            or approval.request_owner_id.id != request.env.user.id
        ):
            raise AccessError(_("Request not found or access denied."))
        return approval

    def _status_label(self, status):
        return {
            "new": _("To Submit"),
            "pending": _("Submitted"),
            "approved": _("Approved"),
            "refused": _("Refused"),
            "cancel": _("Canceled"),
        }.get(status, status or "")

    @http.route("/my/customer-requests/create", type="http", auth="user", website=True)
    def portal_customer_request_create(self, **kwargs):
        self._ensure_access()
        return request.render(
            "approvals_create_customer.portal_customer_request_create",
            {"page_name": "portal_customer_request_create"},
        )

    @http.route(
        ["/my/customer-requests", "/my/customer-requests/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_customer_request_list(self, page=1, **kwargs):
        self._ensure_access()
        Approval = request.env["approval.request"].sudo()
        domain = [
            ("request_owner_id", "=", request.env.user.id),
            ("approval_type", "=", "create_customer"),
        ]
        total = Approval.search_count(domain)
        pager = portal_pager(
            url="/my/customer-requests",
            total=total,
            page=page,
            step=20,
            url_args={},
        )
        approvals = Approval.search(
            domain,
            order="create_date desc, id desc",
            limit=20,
            offset=pager["offset"],
        )
        return request.render(
            "approvals_create_customer.portal_customer_request_list",
            {
                "page_name": "portal_customer_request_list",
                "approvals": approvals,
                "pager": pager,
                "status_label": self._status_label,
            },
        )

    @http.route("/my/customer-requests/<int:request_id>", type="http", auth="user", website=True)
    def portal_customer_request_detail(self, request_id, **kwargs):
        self._ensure_access()
        approval = self._get_my_request(request_id)
        return request.render(
            "approvals_create_customer.portal_customer_request_detail",
            {
                "page_name": "portal_customer_request_detail",
                "approval": approval,
                "status_label": self._status_label(approval.request_status),
            },
        )

    @http.route("/my/customer-requests/api/submit", type="jsonrpc", auth="user", website=True)
    def api_submit(self, name="", phone="", email="", **kwargs):
        self._ensure_access()
        return self._submit_request(name, phone, email)

    @http.route(
        "/my/customer-requests/api/submit/http",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def api_submit_http(self, **kwargs):
        self._ensure_access()
        payload = request.get_json_data() if request.httprequest.is_json else kwargs
        result = self._submit_request(
            payload.get("name", ""),
            payload.get("phone", ""),
            payload.get("email", ""),
        )
        return request.make_json_response(result)

    def _submit_request(self, name, phone, email):
        name = (name or "").strip()
        phone = (phone or "").strip()
        email = (email or "").strip()
        if not name:
            raise UserError(_("Customer name is required."))
        if email and not EMAIL_RE.match(email):
            raise UserError(_("Please enter a valid email address."))

        category = self._get_category()
        Approval = request.env["approval.request"].sudo()
        vals = {
            "category_id": category.id,
            "request_owner_id": request.env.user.id,
            "customer_name": name,
            "customer_phone": phone or False,
            "customer_email": email or False,
            "reason": _("Portal customer request: %(name)s", name=name),
        }
        if not category.automated_sequence:
            vals["name"] = _("New Customer: %(name)s", name=name)

        approval = False
        try:
            approval = Approval.create(vals)
            approval.action_confirm()
        except (UserError, ValidationError):
            if approval:
                try:
                    approval.unlink()
                except Exception:
                    _logger.exception("Could not rollback draft customer approval %s", approval.id)
            raise
        except Exception:
            if approval:
                try:
                    approval.unlink()
                except Exception:
                    _logger.exception("Could not rollback draft customer approval %s", approval.id)
            _logger.exception("Failed to submit create-customer approval from portal")
            raise UserError(_("Could not submit the request. Please try again or contact an administrator."))

        return {
            "id": approval.id,
            "name": approval.name,
            "redirect_url": f"/my/customer-requests/{approval.id}",
        }

    @http.route("/my/customer-requests/api/cancel", type="jsonrpc", auth="user", website=True)
    def api_cancel(self, request_id=None, **kwargs):
        self._ensure_access()
        return self._cancel_request(request_id)

    @http.route(
        "/my/customer-requests/api/cancel/http",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def api_cancel_http(self, **kwargs):
        self._ensure_access()
        payload = request.get_json_data() if request.httprequest.is_json else kwargs
        result = self._cancel_request(payload.get("request_id"))
        return request.make_json_response(result)

    def _cancel_request(self, request_id):
        approval = self._get_my_request(request_id)
        if approval.request_status in ("approved", "cancel"):
            raise UserError(_("This request can no longer be canceled."))
        if approval.created_partner_id:
            raise UserError(_("This request already created a customer and cannot be canceled."))
        try:
            if approval.request_status == "new":
                approval.mapped("approver_ids").write({"status": "cancel"})
            else:
                approval.action_cancel()
        except (UserError, ValidationError):
            raise
        except Exception:
            _logger.exception("Failed to cancel create-customer approval from portal")
            raise UserError(_("Could not cancel the request."))
        return {"ok": True, "status": approval.request_status}
