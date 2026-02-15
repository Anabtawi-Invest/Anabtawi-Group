# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # -----------------------------------------------------
    # Badge
    # -----------------------------------------------------
    reconciliation_state = fields.Selection(
        [("pending", "Pending"), ("reconciled", "Reconciled")],
        default="pending",
        string="Reconcile Status",
        tracking=True,
        copy=False,
    )

    # -----------------------------------------------------
    # Metrics (computed, no store needed for UI columns)
    # -----------------------------------------------------
    late_hours = fields.Float(string="Late Hours", compute="_compute_recon_metrics")
    ot_total_hours = fields.Float(string="OT Total (Hours)", compute="_compute_recon_metrics")
    leave_hours_available = fields.Float(string="Annual Leave (Hours)", compute="_compute_recon_metrics")

    # Results written by reconcile button
    ot_deduct_hours = fields.Float(string="OT Deduction (Hours)", readonly=True, copy=False)
    leave_deduct_hours = fields.Float(string="Leave Deduction (Hours)", readonly=True, copy=False)
    salary_deduct_hours = fields.Float(string="Salary Deduction (Hours)", readonly=True, copy=False)

    @api.depends(
        "employee_id",
        "date_from",
        "date_to",
        "worked_days_line_ids.code",
        "worked_days_line_ids.number_of_hours",
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

            # remaining_leaves usually in days → convert to hours
            hpd = 8.0
            if slip.employee_id and slip.employee_id.resource_calendar_id:
                hpd = slip.employee_id.resource_calendar_id.hours_per_day or 8.0

            leave_days = slip.employee_id.remaining_leaves if slip.employee_id else 0.0
            leave_hours = (leave_days or 0.0) * hpd

            slip.late_hours = late
            slip.ot_total_hours = ot
            slip.leave_hours_available = leave_hours

    # -----------------------------------------------------
    # Live badge reset (SAFE)
    # -----------------------------------------------------
    def _set_pending_if_reconciled(self):
        slips = self.filtered(lambda s: s.reconciliation_state == "reconciled")
        if slips:
            # avoid recursive reset loop
            super(HrPayslip, slips.with_context(skip_recon_reset=True)).write(
                {"reconciliation_state": "pending"}
            )

  def write(self, vals):
    # Prevent recursive reset loop
    if self.env.context.get("skip_recon_reset"):
        return super(HrPayslip, self).write(vals)

    res = super(HrPayslip, self).write(vals)

    trigger_fields = {
        "worked_days_line_ids",
        "input_line_ids",
        "line_ids",
        "date_from",
        "date_to",
        "employee_id",
    }

    if trigger_fields.intersection(vals.keys()):
        slips = self.filtered(lambda s: s.reconciliation_state == "reconciled")
        if slips:
            super(HrPayslip, slips.with_context(skip_recon_reset=True)).write({
                "reconciliation_state": "pending"
            })

    return res

    # -----------------------------------------------------
    # Reconcile button (OT -> Leave -> Salary)
    # -----------------------------------------------------
    def action_reconcile_lateness_engine_v2(self):
        for slip in self:
            late = slip.late_hours or 0.0
            ot_avail = slip.ot_total_hours or 0.0
            leave_avail = slip.leave_hours_available or 0.0

            ot_used = 0.0
            leave_used = 0.0
            sal_used = 0.0

            if late > 0 and ot_avail > 0:
                ot_used = min(late, ot_avail)
                late -= ot_used

            if late > 0 and leave_avail > 0:
                leave_used = min(late, leave_avail)
                late -= leave_used

            if late > 0:
                sal_used = late

            slip.write({
                "ot_deduct_hours": ot_used,
                "leave_deduct_hours": leave_used,
                "salary_deduct_hours": sal_used,
                "reconciliation_state": "reconciled",
            })

        return True

    # -----------------------------------------------------
    # Payroll Control Engine: block validation if pending
    # -----------------------------------------------------
    def _ensure_reconciled(self):
        pending = self.filtered(lambda s: s.reconciliation_state != "reconciled")
        if pending:
            names = ", ".join(pending.mapped("employee_id.name"))
            raise UserError(
                _("Cannot validate because reconciliation is Pending for: %s\n"
                  "Press Reconcile on the payslip(s) first.") % names
            )

    def action_payslip_done(self):
        self._ensure_reconciled()
        return super().action_payslip_done()

    # extra safety for different flows
    def action_validate(self):
        self._ensure_reconciled()
        return super().action_validate()

    def action_validate_sheet(self):
        self._ensure_reconciled()
        return super().action_validate_sheet()
