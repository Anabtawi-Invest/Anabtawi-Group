# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # HR dashboard (before reconciliation)
    lateness_hours = fields.Float(string="Lateness (Hours)", compute="_compute_recon_dashboard", store=True)
    ot_total_hours = fields.Float(string="OT Total (Hours)", compute="_compute_recon_dashboard", store=True)
    annual_leave_hours = fields.Float(string="Annual Leave (Hours)", compute="_compute_recon_dashboard", store=True)

    # Results after reconciliation
    remaining_after_reconciliation_hours = fields.Float(string="Remaining (Hours)", readonly=True)
    recon_ot_used_hours = fields.Float(string="OT Used (Hours)", readonly=True)
    recon_leave_used_hours = fields.Float(string="Leave Used (Hours)", readonly=True)

    # v19.2 SAFE: store the delta we applied to employee bank to prevent double counting
    recon_bank_delta_hours = fields.Float(string="Bank Delta (Hours)", readonly=True, help="Net bank change applied by reconciliation.")
    reconciliation_state = fields.Selection(
        [("not_reconciled", "Not Reconciled"), ("reconciled", "Reconciled")],
        default="not_reconciled",
        readonly=True,
        copy=False,
    )
    reconciliation_date = fields.Datetime(readonly=True, copy=False)

    # Helpful identifiers for list views
    employee_identification_id = fields.Char(related="employee_id.identification_id", string="ID Number", readonly=True, store=True)
    employee_barcode = fields.Char(related="employee_id.barcode", string="Employee No.", readonly=True, store=True)

    # -----------------------------------------------------
    # Odoo 19 SAFE annual leave balance
    # -----------------------------------------------------
    def _get_employee_annual_leave_days_safe(self, employee):
        """
        Odoo 19 safe: 'remaining_leaves' is not a simple stored field on hr.employee.
        We try _get_remaining_leaves() and fallback to 0.0.
        """
        try:
            data = employee._get_remaining_leaves()
            if isinstance(data, dict):
                emp_data = data.get(employee.id) or {}
                # Most common key:
                if emp_data.get("remaining_leaves") is not None:
                    return float(emp_data.get("remaining_leaves") or 0.0)
        except Exception:
            pass
        return 0.0

    # -----------------------------------------------------
    # Dashboard compute
    # -----------------------------------------------------
    @api.depends(
        "worked_days_line_ids.number_of_hours",
        "worked_days_line_ids.code",
        "employee_id.resource_calendar_id",
    )
    def _compute_recon_dashboard(self):
        for slip in self:
            lat = 0.0
            ot = 0.0

            for wd in slip.worked_days_line_ids:
                if wd.code == "LAT":
                    lat += wd.number_of_hours or 0.0
                elif wd.code in ("OTW", "OTR", "PHO"):
                    ot += wd.number_of_hours or 0.0

            hours_per_day = slip.employee_id.resource_calendar_id.hours_per_day if slip.employee_id.resource_calendar_id else 8.0
            remaining_leave_days = slip._get_employee_annual_leave_days_safe(slip.employee_id)
            leave_hours = remaining_leave_days * hours_per_day

            slip.lateness_hours = lat
            slip.ot_total_hours = ot
            slip.annual_leave_hours = leave_hours

    # -----------------------------------------------------
    # v19.2 SAFE RECONCILIATION (IDEMPOTENT)
    # -----------------------------------------------------
    def action_reconcile_lateness(self):
        """
        One-click reconciliation (SAFE / idempotent):
        - Reads LAT (lateness) + OTW/OTR/PHO (OT approved) hours
        - Uses OT bank first, then annual leave hours, then leaves remaining hours
        - Updates employee overtime_bank_hours with a delta that is stored on the payslip
        - If HR presses again: revert old delta first, then re-apply new delta (no double counting)
        """
        for slip in self:
            if slip.state not in ("draft", "verify"):
                raise UserError(_("Reconciliation is only allowed in Draft or Waiting states."))

            slip._compute_recon_dashboard()

            employee = slip.employee_id.sudo()
            current_bank = employee.overtime_bank_hours or 0.0

            # v19.2 SAFE STEP A: if already reconciled, revert previous applied delta first
            old_delta = slip.recon_bank_delta_hours or 0.0
            if slip.reconciliation_state == "reconciled" and old_delta:
                current_bank -= old_delta  # revert net change from previous run

            # v19.2 STEP B: compute reconciliation using the reverted bank
            lateness = slip.lateness_hours or 0.0
            approved_ot = slip.ot_total_hours or 0.0

            # OT gets banked for this period, but might be consumed by lateness
            bank_after_banking = current_bank + approved_ot

            remaining = lateness

            # Deduct from OT bank first
            ot_used = min(remaining, bank_after_banking)
            bank_after_ot = bank_after_banking - ot_used
            remaining -= ot_used

            # Deduct from annual leave hours (display-only; not creating leave request here)
            leave_avail = slip.annual_leave_hours or 0.0
            leave_used = min(remaining, leave_avail)
            remaining -= leave_used

            # Net delta we apply to employee bank this run:
            # bank_after_ot - current_bank  == approved_ot - ot_used
            new_delta = bank_after_ot - current_bank

            # v19.2 STEP C: persist results
            slip.write({
                "remaining_after_reconciliation_hours": remaining,
                "recon_ot_used_hours": ot_used,
                "recon_leave_used_hours": leave_used,
                "recon_bank_delta_hours": new_delta,
                "reconciliation_state": "reconciled",
                "reconciliation_date": fields.Datetime.now(),
            })

            employee.write({"overtime_bank_hours": current_bank + new_delta})

            # Recompute payslip so any salary rules that depend on remaining hours reflect instantly
            slip.compute_sheet()
