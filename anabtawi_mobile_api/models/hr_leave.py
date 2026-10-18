import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)

# Contexts used by payroll_fix_recon / hr_leave_fallback to create system leaves
# (lateness settlement, auto allocation). They must never page a manager.
SYSTEM_LEAVE_CONTEXT_KEYS = (
    "leave_fast_create", "leave_skip_state_check", "no_work_entry",
)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    # ------------------------------------------------------------------
    # Approver helpers (used by the notification hooks and the API)
    # ------------------------------------------------------------------
    def _mobile_stage_one_users(self):
        """Users who must act first on a request in state 'confirm'."""
        self.ensure_one()
        vtype = self.holiday_status_id.leave_validation_type
        if vtype in ("manager", "both"):
            manager = self.employee_id.leave_manager_id
            if manager and manager != self.employee_id.user_id:
                return manager
            return self.holiday_status_id.responsible_ids
        if vtype == "hr":
            return self.holiday_status_id.responsible_ids
        return self.env["res.users"]

    def _mobile_hr_users(self):
        self.ensure_one()
        return self.holiday_status_id.responsible_ids

    def _mobile_is_system_context(self):
        return any(self.env.context.get(key) for key in SYSTEM_LEAVE_CONTEXT_KEYS)

    def _mobile_notify(self, users, kind, title, body=""):
        self.ensure_one()
        self.env["anabtawi.mobile.notification"].push(users, kind, title, body, record=self)

    def _mobile_summary(self):
        self.ensure_one()
        return "%s: %s → %s" % (
            self.holiday_status_id.name,
            self.request_date_from or "",
            self.request_date_to or "",
        )

    # ------------------------------------------------------------------
    # Workflow hooks
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        if self._mobile_is_system_context():
            return leaves
        for leave in leaves.filtered(lambda rec: rec.state == "confirm"):
            try:
                approvers = leave._mobile_stage_one_users()
                leave._mobile_notify(
                    approvers,
                    "leave_request",
                    _("%(employee)s requested time off", employee=leave.employee_id.name),
                    leave._mobile_summary(),
                )
            except Exception:
                _logger.exception("Leave %s: approver notification failed", leave.id)
        return leaves

    def action_approve(self, check_state=True):
        before = {leave.id: leave.state for leave in self}
        res = super().action_approve(check_state=check_state)
        if not self._mobile_is_system_context():
            for leave in self.filtered(lambda rec: before.get(rec.id) == "confirm"):
                try:
                    leave._mobile_after_approve()
                except Exception:
                    _logger.exception("Leave %s: approve notification failed", leave.id)
        return res

    def _mobile_after_approve(self):
        self.ensure_one()
        employee_user = self.employee_id.user_id
        if self.state == "validate1":
            # manager done, HR still has to confirm
            self._mobile_notify(
                employee_user, "leave_approved",
                _("Your time off was approved by your manager"),
                _("Waiting for HR confirmation. %s", self._mobile_summary()),
            )
            self._mobile_notify(
                self._mobile_hr_users(), "leave_hr",
                _("%(employee)s: time off ready for HR confirmation", employee=self.employee_id.name),
                self._mobile_summary(),
            )

    def _action_validate(self, check_state=True):
        before = {leave.id: leave.state for leave in self}
        res = super()._action_validate(check_state=check_state)
        if not self._mobile_is_system_context():
            for leave in self.filtered(lambda rec: before.get(rec.id) != "validate" and rec.state == "validate"):
                try:
                    leave._mobile_notify(
                        leave.employee_id.user_id, "leave_validated",
                        _("Your time off is confirmed"), leave._mobile_summary(),
                    )
                except Exception:
                    _logger.exception("Leave %s: validate notification failed", leave.id)
        return res

    def action_refuse(self):
        before = {leave.id: leave.state for leave in self}
        res = super().action_refuse()
        if not self._mobile_is_system_context():
            for leave in self.filtered(lambda rec: before.get(rec.id) != "refuse" and rec.state == "refuse"):
                try:
                    leave._mobile_notify(
                        leave.employee_id.user_id, "leave_refused",
                        _("Your time off was refused"), leave._mobile_summary(),
                    )
                except Exception:
                    _logger.exception("Leave %s: refuse notification failed", leave.id)
        return res
