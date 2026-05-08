# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import datetime, time

from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_logger = logging.getLogger(__name__)


class OvertimeApprovalPortal(CustomerPortal):
    _overtime_portal_step = 20

    def _overtime_portal_employee(self):
        return (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )

    def _overtime_portal_categories(self, employee):
        company = employee.company_id or request.env.company
        Category = request.env["approval.category"].sudo()
        domain = [("is_overtime_category", "=", True)]
        if "company_id" in Category._fields:
            domain = domain + [
                "|",
                ("company_id", "=", False),
                ("company_id", "=", company.id),
            ]
        categories = Category.search(domain)
        if not categories:
            self._overtime_portal_log_no_categories(employee, domain, categories)
        return categories

    def _overtime_portal_log_no_categories(self, employee, domain, categories):
        """Explain empty category list for portal /my/overtime_approvals/new."""
        user = request.env.user
        session_company = request.env.company
        emp_company = employee.company_id
        Category = request.env["approval.category"].sudo()

        all_ot = Category.search([("is_overtime_category", "=", True)])
        lines = [
            "user_id=%s login=%r",
            "employee_id=%s name=%r company_id=%s company_name=%r",
            "request.env.company_id=%s (session/website company)",
            "search domain=%s → count=%s",
            "all is_overtime_category (no company filter in this query): count=%s",
        ]
        args = [
            user.id,
            user.login,
            employee.id,
            employee.name,
            emp_company.id if emp_company else None,
            emp_company.name if emp_company else None,
            session_company.id if session_company else None,
            domain,
            len(categories),
            len(all_ot),
        ]
        has_company = "company_id" in Category._fields
        for rec in all_ot:
            if has_company:
                cid = rec.company_id.id if rec.company_id else None
                cname = rec.company_id.name if rec.company_id else None
            else:
                cid = cname = None
            args.extend([rec.id, rec.name, cid, cname])
            lines.append("  overtime category id=%s name=%r company_id=%s company_name=%r")

        _logger.warning(
            "Overtime portal: no categories for user; " + "; ".join(lines), *args
        )

    def _overtime_portal_requests_domain(self):
        return [
            ("request_owner_id", "=", request.env.user.id),
            ("category_id.is_overtime_category", "=", True),
        ]

    def _overtime_portal_get_request(self, request_id):
        req = request.env["approval.request"].sudo().browse(int(request_id))
        if not req.exists() or req.request_owner_id != request.env.user:
            raise NotFound()
        if not req.category_id.is_overtime_category:
            raise NotFound()
        return req

    def _overtime_portal_pop_session_message(self, key):
        return request.session.pop(key, None)

    @http.route(
        ["/my/overtime_approvals", "/my/overtime_approvals/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
        readonly=True,
    )
    def portal_my_overtime_approvals(self, page=1, **kw):
        employee = self._overtime_portal_employee()
        if not employee:
            vals = self._prepare_portal_layout_values()
            vals.update(
                {
                    "page_name": "overtime_approval",
                    "error_message": _("No employee is linked to your user account."),
                }
            )
            return request.render(
                "hr_attendance_overtime_approval_bridge.portal_overtime_no_employee",
                vals,
            )

        Approval = request.env["approval.request"].sudo()
        domain = self._overtime_portal_requests_domain()
        total = Approval.search_count(domain)
        pager_vals = portal_pager(
            url="/my/overtime_approvals",
            total=total,
            page=page,
            step=self._overtime_portal_step,
        )
        requests_list = Approval.search(
            domain,
            order="create_date desc, id desc",
            limit=self._overtime_portal_step,
            offset=pager_vals["offset"],
        )
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "overtime_approval",
                "overtime_requests": requests_list,
                "pager": pager_vals,
                "employee": employee,
                "success_message": self._overtime_portal_pop_session_message("overtime_portal_success"),
                "error_message": self._overtime_portal_pop_session_message("overtime_portal_error"),
            }
        )
        return request.render("hr_attendance_overtime_approval_bridge.portal_overtime_list", values)

    @http.route(
        "/my/overtime_approvals/new",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        readonly=True,
    )
    def portal_my_overtime_approvals_new(self, **kw):
        employee = self._overtime_portal_employee()
        if not employee:
            vals = self._prepare_portal_layout_values()
            vals.update(
                {
                    "page_name": "overtime_approval",
                    "error_message": _("No employee is linked to your user account."),
                }
            )
            return request.render(
                "hr_attendance_overtime_approval_bridge.portal_overtime_no_employee",
                vals,
            )
        categories = self._overtime_portal_categories(employee)
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "overtime_approval",
                "employee": employee,
                "categories": categories,
                "success_message": self._overtime_portal_pop_session_message("overtime_portal_success"),
                "error_message": self._overtime_portal_pop_session_message("overtime_portal_error"),
            }
        )
        return request.render("hr_attendance_overtime_approval_bridge.portal_overtime_new", values)

    @http.route(
        "/my/overtime_approvals/new",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_my_overtime_approvals_new_submit(self, **post):
        employee = self._overtime_portal_employee()
        if not employee:
            raise NotFound()

        try:
            category_id = int(post.get("category_id") or 0)
        except (TypeError, ValueError):
            category_id = 0
        category = request.env["approval.category"].sudo().browse(category_id)
        if not category.exists() or not category.is_overtime_category:
            request.session["overtime_portal_error"] = _("Please choose a valid overtime approval type.")
            return request.redirect("/my/overtime_approvals/new")
        if "company_id" in category._fields and category.company_id and category.company_id != employee.company_id:
            request.session["overtime_portal_error"] = _("This approval type is not available for your company.")
            return request.redirect("/my/overtime_approvals/new")

        date_from_s = (post.get("overtime_date_from") or "").strip()
        date_to_s = (post.get("overtime_date_to") or "").strip()
        try:
            overtime_date_from = fields.Date.from_string(date_from_s)
            overtime_date_to = fields.Date.from_string(date_to_s)
        except ValueError:
            request.session["overtime_portal_error"] = _("Invalid dates.")
            return request.redirect("/my/overtime_approvals/new")

        try:
            quantity = float((post.get("quantity") or "0").replace(",", "."))
        except ValueError:
            quantity = 0.0
        if quantity <= 0:
            request.session["overtime_portal_error"] = _("Requested hours must be greater than zero.")
            return request.redirect("/my/overtime_approvals/new")

        name = (post.get("name") or "").strip() or _(
            "Overtime approval — %(employee)s",
            employee=employee.name,
        )
        company = employee.company_id or request.env.company
        vals = {
            "name": name,
            "category_id": category.id,
            "request_owner_id": request.env.user.id,
            "company_id": company.id,
            "overtime_employee_id": employee.id,
            "overtime_date_from": overtime_date_from,
            "overtime_date_to": overtime_date_to,
            "quantity": quantity,
            "date": overtime_date_from,
            "date_start": datetime.combine(overtime_date_from, time.min),
            "date_end": datetime.combine(overtime_date_to, time.max),
        }
        try:
            approval = request.env["approval.request"].sudo().create(vals)
        except (UserError, ValidationError) as e:
            request.session["overtime_portal_error"] = e.args[0] if e.args else str(e)
            return request.redirect("/my/overtime_approvals/new")

        request.session["overtime_portal_success"] = _("Your request was saved. Submit it when you are ready.")
        return request.redirect(f"/my/overtime_approvals/{approval.id}")

    @http.route(
        "/my/overtime_approvals/<int:request_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        readonly=True,
    )
    def portal_my_overtime_approval_detail(self, request_id, **kw):
        approval = self._overtime_portal_get_request(request_id)

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "overtime_approval",
                "approval": approval,
                "success_message": self._overtime_portal_pop_session_message("overtime_portal_success"),
                "error_message": self._overtime_portal_pop_session_message("overtime_portal_error"),
            }
        )
        return request.render("hr_attendance_overtime_approval_bridge.portal_overtime_detail", values)

    @http.route(
        "/my/overtime_approvals/<int:request_id>/submit",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_my_overtime_approval_submit(self, request_id, **post):
        approval = self._overtime_portal_get_request(request_id)

        if approval.request_status != "new":
            request.session["overtime_portal_error"] = _("This request can no longer be submitted from the portal.")
            return request.redirect(f"/my/overtime_approvals/{approval.id}")

        try:
            approval.action_confirm()
        except (UserError, ValidationError) as e:
            request.session["overtime_portal_error"] = e.args[0] if e.args else str(e)
            return request.redirect(f"/my/overtime_approvals/{approval.id}")

        request.session["overtime_portal_success"] = _("Your request was sent to your attendance manager for approval.")
        return request.redirect(f"/my/overtime_approvals/{approval.id}")
