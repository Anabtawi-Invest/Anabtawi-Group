# -*- coding: utf-8 -*-
import base64
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
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024  # 15 MB per file
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".doc",
    ".docx",
}


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
                ("company_id", "in", [False, company.id]),
                ("active", "=", True),
            ],
            order="company_id desc, id",
            limit=1,
        )
        if not category:
            # env.ref uses the portal user env (no ACL on approval.category) — always sudo.
            category = request.env.ref(CATEGORY_XMLID, raise_if_not_found=False)
            if category:
                category = Category.browse(category.id)
        if not category or not category.exists() or not category.active:
            raise UserError(
                _("Create Customer approval category is not configured. Please contact an administrator.")
            )
        # Portal create-customer must NOT use approval_contact mandatory VAT/attachment rules
        if "x_create_contact_on_approve" in category._fields and category.x_create_contact_on_approve:
            category.sudo().write({"x_create_contact_on_approve": False})
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

    def _get_request_attachments(self, approval):
        return (
            request.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "approval.request"),
                    ("res_id", "=", approval.id),
                    ("res_field", "=", False),
                ],
                order="id",
            )
        )

    def _status_label(self, status):
        return {
            "new": _("To Submit"),
            "pending": _("Submitted"),
            "approved": _("Approved"),
            "refused": _("Refused"),
            "cancel": _("Canceled"),
        }.get(status, status or "")

    def _normalize_attachments(self, attachments):
        if not attachments:
            return []
        if not isinstance(attachments, (list, tuple)):
            raise UserError(_("Invalid commercial register attachments."))
        cleaned = []
        for item in attachments:
            if not isinstance(item, dict):
                raise UserError(_("Invalid commercial register attachments."))
            name = (item.get("name") or "").strip()
            datas = item.get("datas") or ""
            if isinstance(datas, str) and datas.startswith("data:") and "," in datas:
                datas = datas.split(",", 1)[1]
            datas = (datas or "").strip()
            mimetype = (item.get("mimetype") or "application/octet-stream").strip()
            if not name or not datas:
                continue
            ext = ""
            if "." in name:
                ext = "." + name.rsplit(".", 1)[-1].lower()
            if ext and ext not in ALLOWED_EXTENSIONS:
                raise UserError(
                    _("File type %(ext)s is not allowed for Commercial Register.", ext=ext)
                )
            try:
                raw = base64.b64decode(datas, validate=False)
            except Exception as exc:
                raise UserError(_("One of the attached files is invalid.")) from exc
            if not raw:
                continue
            if len(raw) > MAX_ATTACHMENT_BYTES:
                raise UserError(
                    _("Each Commercial Register file must be %(limit)s MB or smaller.", limit=15)
                )
            cleaned.append(
                {
                    "name": name,
                    "datas": base64.b64encode(raw),
                    "mimetype": mimetype or "application/octet-stream",
                }
            )
        return cleaned

    def _create_attachments(self, approval, attachments):
        Attachment = request.env["ir.attachment"].sudo()
        for item in attachments:
            Attachment.create(
                {
                    "name": item["name"],
                    "datas": item["datas"],
                    "res_model": "approval.request",
                    "res_id": approval.id,
                    "mimetype": item["mimetype"],
                    "description": _("Commercial Register (السجل التجاري)"),
                }
            )
        approval.invalidate_recordset(["attachment_number", "attachment_ids"])

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
                "attachments": self._get_request_attachments(approval),
                "status_label": self._status_label(approval.request_status),
            },
        )

    @http.route(
        "/my/customer-requests/<int:request_id>/attachment/<int:attachment_id>",
        type="http",
        auth="user",
        website=True,
    )
    def portal_customer_request_attachment(self, request_id, attachment_id, **kwargs):
        self._ensure_access()
        approval = self._get_my_request(request_id)
        attachment = (
            request.env["ir.attachment"]
            .sudo()
            .browse(int(attachment_id))
            .exists()
        )
        if (
            not attachment
            or attachment.res_model != "approval.request"
            or attachment.res_id != approval.id
        ):
            raise AccessError(_("Attachment not found or access denied."))
        return request.env["ir.binary"]._get_stream_from(attachment).get_response(as_attachment=True)

    @http.route("/my/customer-requests/api/submit", type="jsonrpc", auth="user", website=True)
    def api_submit(self, name="", phone="", email="", attachments=None, **kwargs):
        self._ensure_access()
        return self._submit_request(name, phone, email, attachments)

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
            payload.get("attachments"),
        )
        return request.make_json_response(result)

    def _submit_request(self, name, phone, email, attachments=None):
        name = (name or "").strip()
        phone = (phone or "").strip()
        email = (email or "").strip()
        if not name:
            raise UserError(_("Customer name is required."))
        if email and not EMAIL_RE.match(email):
            raise UserError(_("Please enter a valid email address."))

        cleaned_attachments = self._normalize_attachments(attachments)
        if not cleaned_attachments:
            raise UserError(
                _("Please attach at least one Commercial Register (السجل التجاري) document.")
            )

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
            self._create_attachments(approval, cleaned_attachments)
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
