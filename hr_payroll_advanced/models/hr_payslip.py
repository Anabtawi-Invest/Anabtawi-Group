# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # -----------------------------------------------------
    # Reconciliation status badge
    # -----------------------------------------------------
    reconciliation_state = fields.Selection(
        [("pending", "Pending"), ("reconciled", "Reconciled")],
        default="pending",
        string="Reconcile Status",
        tracking=True,
        copy=False,
    )

    # -----------------------------------------------------
    # Metrics (hours) shown to HR (safe, no currency fields)
    # -----------------------------------------------------
    late_hours = fields.Float(string="Late Hours", compute="_compute_recon_metrics", store=False)
    ot_total_hours = fields.Float(string="OT Total (Hours)", compute="_compute_recon_metrics", store=False)
    leave_hours_available = fields.Float(string="Annual Leave (Hours)", compute="_compute_recon_metrics", store=False)

    ot_deduct_hours = fields.Float(string="OT Deduction (Hours)", readonly=True, copy=False)
    leave_deduct_hours = fields.Float(string="Leave Deduction (Hours)", readonly=True, copy=False)
    salary_deduct_hours = fields.Float(string="Salary Deduction (Hours)", readonly=True, copy=False)

    @api.depends(
        "employee_id",
        "date_from",
        "date_to",
        "worked_days_line_ids.number_of_hours",
        "worked_days_line_ids.code",
        "employee_id.remaining_leaves",
        "employee_id.resource_calendar_id.hours_per_day",
    )
    def _compute_recon_metrics(self):
        for slip in self:
            late = 0.0
            ot = 0.0
            for wd in slip.worked_days_line_ids:
                code = (wd.code or "").strip().upper()
                hrs = wd.number_of_hours or 0.0
                if code == "LAT":
                    late += hrs
                elif code in ("OTW", "OTR", "PHO"):
                    ot += hrs

            # remaining_leaves is usually in days; convert to hours using calendar hours/day (fallback 8)
            hpd = (slip.employee_id.resource_calendar_id.hours_per_day or 8.0) if slip.employee_id else 8.0
            leave_days = slip.employee_id.remaining_leaves if slip.employee_id else 0.0
            leave_hours = (leave_days or 0.0) * hpd

            slip.late_hours = late
            slip.ot_total_hours = ot
            slip.leave_hours_available = leave_hours

    # -----------------------------------------------------
    # Live badge reset: if anything relevant changes, badge -> pending
    # (safe: no overriding core compute methods)
    # -----------------------------------------------------
    def _reset_reconcile_if_changed(self):
        for slip in self:
            if slip.reconciliation_state == "reconciled":
                slip.reconciliation_state = "pending"

    def write(self, vals):
        res = super().write(vals)
        # If HR/engine touches payroll inputs/worked days/lines, reconciliation must be re-done.
        trigger_fields = {"worked_days_line_ids", "input_line_ids", "line_ids", "date_from", "date_to", "employee_id"}
        if trigger_fields.intersection(vals.keys()):
            self._reset_reconcile_if_changed()
        return res

    def compute_sheet(self):
        res = super().compute_sheet()
        self._reset_reconcile_if_changed()
        return res

    # -----------------------------------------------------
    # Payroll control: block validation if not reconciled
    # -----------------------------------------------------
    def _ensure_reconciled_before_validate(self):
        pending = self.filtered(lambda s: s.reconciliation_state != "reconciled")
        if pending:
            names = ", ".join(pending.mapped("employee_id.name"))
            raise UserError(
                "Cannot validate payslip(s) because reconciliation is still Pending for: %s\n"
                "Please press Reconcile first." % (names,)
            )

    def action_payslip_done(self):
        self._ensure_reconciled_before_validate()
        return super().action_payslip_done()

    # Some databases/flows use these names; keep safe fallbacks.
    def action_validate(self):
        self._ensure_reconciled_before_validate()
        return super().action_validate()

    def action_validate_sheet(self):
        self._ensure_reconciled_before_validate()
        return super().action_validate_sheet()

    # -----------------------------------------------------
    # Reconciliation Engine v2 (hours-based)
    # OT -> Annual Leave -> Salary
    # -----------------------------------------------------
    def action_reconcile_lateness_engine_v2(self):
        for slip in self:
            late = slip.late_hours or 0.0
            ot_avail = slip.ot_total_hours or 0.0
            leave_avail = slip.leave_hours_available or 0.0

            ot_deduct = 0.0
            leave_deduct = 0.0
            sal_deduct = 0.0

            if late > 0 and ot_avail > 0:
                ot_deduct = min(late, ot_avail)
                late -= ot_deduct

            if late > 0 and leave_avail > 0:
                leave_deduct = min(late, leave_avail)
                late -= leave_deduct

            if late > 0:
                sal_deduct = late

            slip.write({
                "ot_deduct_hours": ot_deduct,
                "leave_deduct_hours": leave_deduct,
                "salary_deduct_hours": sal_deduct,
                "reconciliation_state": "reconciled",
            })
        return True
