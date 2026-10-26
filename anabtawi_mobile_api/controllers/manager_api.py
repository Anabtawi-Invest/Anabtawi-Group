import logging

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import html2plaintext

from .mobile_api import AnabtawiMobileAPI, _error, _json, _payload

_logger = logging.getLogger(__name__)

OFFICER_GROUP = "hr_holidays.group_hr_holidays_user"


class AnabtawiMobileManagerAPI(http.Controller):
    """Manager approval endpoints for the Employee App.

    Only requests of the caller's own team are listed. Approval is the first
    level only (Odoo leave state ``confirm``); the second-level HR validation
    stays in Odoo unless the caller is a Time Off officer.
    """

    # ------------------------------------------------------------------ helpers
    def _auth(self):
        return AnabtawiMobileAPI()._require_employee()

    def _is_officer(self, user):
        try:
            return bool(user.sudo().has_group(OFFICER_GROUP))
        except Exception:
            return False

    def _team_domain(self, user):
        return [
            ("active", "=", True),
            "|",
            ("leave_manager_id", "=", user.id),
            ("parent_id.user_id", "=", user.id),
        ]

    def _team_employees(self, user, own_employee):
        employees = request.env["hr.employee"].sudo().search(self._team_domain(user))
        return employees - own_employee

    def _can_manage_employee(self, user, employee):
        if employee.user_id == user:
            return False
        return (
            employee.leave_manager_id == user
            or employee.parent_id.user_id == user
        )

    def _pending_leaves(self, user, own_employee):
        officer = self._is_officer(user)
        team = self._team_employees(user, own_employee)
        states = ["confirm", "validate1"] if officer else ["confirm"]
        return request.env["hr.leave"].sudo().search(
            [("employee_id", "in", team.ids), ("state", "in", states)],
            order="request_date_from asc, id asc",
            limit=100,
        )

    def _approver_line(self, approval, user):
        lines = approval.approver_ids.filtered(
            lambda line: line.user_id == user and line.status == "pending"
        )
        return lines[:1]

    def _pending_overtime(self, user):
        Approval = request.env["approval.request"].sudo()
        candidates = Approval.search(
            [("is_overtime_category", "=", True), ("request_status", "=", "pending")],
            order="create_date asc, id asc",
            limit=300,
        )
        return candidates.filtered(lambda approval: self._approver_line(approval, user))

    def _leave_dict(self, leave):
        return {
            "id": leave.id,
            "employee": leave.employee_id.name,
            "employee_id": leave.employee_id.id,
            "type": leave.holiday_status_id.name,
            "reason": leave.name or "",
            "date_from": fields.Date.to_string(leave.request_date_from) if leave.request_date_from else None,
            "date_to": fields.Date.to_string(leave.request_date_to) if leave.request_date_to else None,
            "hour_from": round(leave.request_hour_from, 4) if leave.request_unit_hours else None,
            "hour_to": round(leave.request_hour_to, 4) if leave.request_unit_hours else None,
            "days": round(leave.number_of_days or 0.0, 2),
            "state": leave.state,
        }

    def _overtime_dict(self, approval):
        return {
            "id": approval.id,
            "employee": approval.overtime_employee_id.name or approval.request_owner_id.name,
            "category": approval.category_id.name,
            "reason": html2plaintext(approval.reason or "").strip() if "reason" in approval._fields else "",
            "date_from": fields.Date.to_string(approval.overtime_date_from) if approval.overtime_date_from else None,
            "date_to": fields.Date.to_string(approval.overtime_date_to) if approval.overtime_date_to else None,
            "hours": approval.quantity,
            "state": approval.request_status,
        }

    def _decision_input(self):
        data = _payload()
        try:
            record_id = int(data.get("id") or 0)
        except (TypeError, ValueError):
            record_id = 0
        action = (data.get("action") or "").strip().lower()
        reason = (data.get("reason") or "").strip()
        return record_id, action, reason

    # ---------------------------------------------------------------- endpoints
    @http.route(
        "/anabtawi/mobile/manager/summary",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def manager_summary(self, **kwargs):
        employee, user, _token, error = self._auth()
        if error:
            return error
        team = self._team_employees(user, employee)
        leaves = self._pending_leaves(user, employee) if team else request.env["hr.leave"]
        overtime = self._pending_overtime(user) if "approval.request" in request.env else []
        is_manager = bool(team) or bool(overtime)
        return _json({
            "status": "ok",
            "is_manager": is_manager,
            "team_size": len(team),
            "pending_leaves": len(leaves),
            "pending_overtime": len(overtime),
        })

    @http.route(
        "/anabtawi/mobile/manager/leaves/pending",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def manager_leaves_pending(self, **kwargs):
        employee, user, _token, error = self._auth()
        if error:
            return error
        leaves = self._pending_leaves(user, employee)
        return _json({"status": "ok", "records": [self._leave_dict(leave) for leave in leaves]})

    @http.route(
        "/anabtawi/mobile/manager/leaves/decision",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def manager_leave_decision(self, **kwargs):
        employee, user, _token, error = self._auth()
        if error:
            return error
        leave_id, action, reason = self._decision_input()
        if not leave_id or action not in ("approve", "refuse"):
            return _error("invalid_request", _("A request id and an action (approve or refuse) are required."), 422)
        if action == "refuse" and not reason:
            return _error("invalid_request", _("A reason is required to refuse."), 422)

        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        officer = self._is_officer(user)
        if not leave or not (self._can_manage_employee(user, leave.employee_id) or officer):
            return _error("not_found", _("Request not found or access denied."), 404)
        if leave.employee_id.user_id == user:
            return _error("forbidden", _("You cannot decide on your own request."), 403)
        allowed_states = ("confirm", "validate1") if officer else ("confirm",)
        if leave.state not in allowed_states:
            return _error("invalid_state", _("This request is no longer waiting for your decision."), 409)

        acting = leave.with_user(user).sudo()
        try:
            with request.env.cr.savepoint():
                if action == "approve":
                    if leave.state == "validate1":
                        acting.action_validate()
                    else:
                        acting.action_approve()
                else:
                    acting.action_refuse()
                    acting.message_post(body=_("Refused from the Employee App: %s", reason))
        except (UserError, ValidationError) as exc:
            return _error("validation_error", exc.args[0] if exc.args else str(exc), 422)
        except Exception:
            _logger.exception("Manager leave decision failed leave_id=%s user_id=%s", leave_id, user.id)
            return _error("server_error", _("The decision could not be saved."), 500)
        return _json({"status": "ok", "id": leave.id, "state": leave.state})

    @http.route(
        "/anabtawi/mobile/manager/overtime/pending",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def manager_overtime_pending(self, **kwargs):
        _employee, user, _token, error = self._auth()
        if error:
            return error
        records = self._pending_overtime(user)
        return _json({"status": "ok", "records": [self._overtime_dict(item) for item in records]})

    @http.route(
        "/anabtawi/mobile/manager/overtime/decision",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def manager_overtime_decision(self, **kwargs):
        _employee, user, _token, error = self._auth()
        if error:
            return error
        record_id, action, reason = self._decision_input()
        if not record_id or action not in ("approve", "refuse"):
            return _error("invalid_request", _("A request id and an action (approve or refuse) are required."), 422)
        if action == "refuse" and not reason:
            return _error("invalid_request", _("A reason is required to refuse."), 422)

        approval = request.env["approval.request"].sudo().browse(record_id).exists()
        if not approval or not approval.is_overtime_category:
            return _error("not_found", _("Request not found or access denied."), 404)
        line = self._approver_line(approval, user)
        if not line or approval.request_status != "pending":
            return _error("not_found", _("Request not found or access denied."), 404)

        acting = approval.with_user(user).sudo()
        try:
            with request.env.cr.savepoint():
                if action == "approve":
                    acting.action_approve(approver=line)
                else:
                    acting.action_refuse(approver=line)
                    acting.message_post(body=_("Refused from the Employee App: %s", reason))
        except (UserError, ValidationError) as exc:
            return _error("validation_error", exc.args[0] if exc.args else str(exc), 422)
        except Exception:
            _logger.exception("Manager overtime decision failed id=%s user_id=%s", record_id, user.id)
            return _error("server_error", _("The decision could not be saved."), 500)
        return _json({"status": "ok", "id": approval.id, "state": approval.request_status})
