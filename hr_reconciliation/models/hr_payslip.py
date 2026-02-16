# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Dashboard (before reconciliation)
    lateness_hours = fields.Float(string="Lateness (Hours)", compute="_compute_recon_dashboard", store=True)
    ot_total_hours = fields.Float(string="OT Total (Hours)", compute="_compute_recon_dashboard", store=True)
    annual_leave_hours = fields.Float(string="Annual Leave (Hours)", compute="_compute_recon_dashboard", store=True)

    # Results (after reconciliation)
    remaining_after_reconciliation_hours = fields.Float(string="Remaining (Hours)", readonly=True)
    recon_ot_used_hours = fields.Float(string="OT Used (Hours)", readonly=True)
    recon_leave_used_hours = fields.Float(string="Leave Used (Hours)", readonly=True)

    # Idempotency anchor (prevents OT bank double-counting)
    recon_bank_delta_hours = fields.Float(string="Bank Delta (Hours)", readonly=True)

    reconciliation_state = fields.Selection(
        [("not_reconciled", "Not Reconciled"), ("reconciled", "Reconciled")],
        default="not_reconciled",
        readonly=True,
        copy=False,
    )
    reconciliation_date = fields.Datetime(readonly=True, copy=False)

    # Optional identifiers for HR lists
    employee_identification_id = fields.Char(related="employee_id.identification_id", string="ID Number", readonly=True, store=True)
    employee_barcode = fields.Char(related="employee_id.barcode", string="Employee No.", readonly=True, store=True)

    # -----------------------------------------------------
    # Odoo 19 SAFE: Annual leave remaining days reader
    # -----------------------------------------------------
    def _get_employee_annual_leave_days_safe(self, employee):
        """
        Odoo 19 safe: remaining annual leave is not a stored field on hr.employee.
        We read via _get_remaining_leaves() and fallback to 0.0.
        """
        try:
            data = employee._get_remaining_leaves()
            if isinstance(data, dict):
                emp_data = data.get(employee.id) or {}
                val = emp_data.get("remaining_leaves")
                if val is None:
                    return 0.0
                return float(val or 0.0)
        except Exception:
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
    # FINAL: Idempotent reconciliation button
    # -----------------------------------------------------
    def action_reconcile_lateness(self):
        for slip in self:
            if slip.state not in ("draft", "verify"):
                raise UserError(_("Reconciliation is only allowed in Draft or Waiting states."))

            slip._compute_recon_dashboard()

            employee = slip.employee_id.sudo()
            current_bank = employee.overtime_bank_hours or 0.0

            # Revert old delta if already reconciled (prevents double counting)
            old_delta = slip.recon_bank_delta_hours or 0.0
            if slip.reconciliation_state == "reconciled" and old_delta:
                current_bank -= old_delta

            lateness = slip.lateness_hours or 0.0
            approved_ot = slip.ot_total_hours or 0.0

            # Add OT for this period to bank, then consume by lateness
            bank_after_banking = current_bank + approved_ot

            remaining = lateness

            # 1) OT bank first
            ot_used = min(remaining, bank_after_banking)
            bank_after_ot = bank_after_banking - ot_used
            remaining -= ot_used

            # 2) Annual leave next (hours) - display only, no leave request created here
            leave_avail = slip.annual_leave_hours or 0.0
            leave_used = min(remaining, leave_avail)
            remaining -= leave_used

            # Net bank delta applied this run = approved_ot - ot_used
            new_delta = bank_after_ot - current_bank

            slip.write({
                "remaining_after_reconciliation_hours": remaining,
                "recon_ot_used_hours": ot_used,
                "recon_leave_used_hours": leave_used,
                "recon_bank_delta_hours": new_delta,
                "reconciliation_state": "reconciled",
                "reconciliation_date": fields.Datetime.now(),
            })

            employee.write({"overtime_bank_hours": current_bank + new_delta})

            # Refresh payroll lines immediately
            slip.compute_sheet()
