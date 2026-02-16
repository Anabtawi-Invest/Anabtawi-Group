# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Read-only dashboard fields for HR
    lateness_hours = fields.Float(string="Lateness (Hours)", compute="_compute_recon_dashboard", store=True)
    ot_total_hours = fields.Float(string="OT Total (Hours)", compute="_compute_recon_dashboard", store=True)
    annual_leave_hours = fields.Float(string="Annual Leave (Hours)", compute="_compute_recon_dashboard", store=True)

    # Result fields after reconciliation
    remaining_after_reconciliation_hours = fields.Float(string="Remaining (Hours)", readonly=True)
    recon_ot_used_hours = fields.Float(string="OT Used (Hours)", readonly=True)
    recon_leave_used_hours = fields.Float(string="Leave Used (Hours)", readonly=True)

    reconciliation_state = fields.Selection(
        [("not_reconciled", "Not Reconciled"), ("reconciled", "Reconciled")],
        default="not_reconciled",
        readonly=True,
        copy=False,
    )
    reconciliation_date = fields.Datetime(readonly=True, copy=False)

    # Related identifiers for simple HR lists
    employee_identification_id = fields.Char(related="employee_id.identification_id", string="ID Number", readonly=True, store=True)
    employee_barcode = fields.Char(related="employee_id.barcode", string="Employee No.", readonly=True, store=True)

    @api.depends("worked_days_line_ids.number_of_hours", "worked_days_line_ids.code", "employee_id.resource_calendar_id")
    def _compute_recon_dashboard(self):
        for slip in self:
            lat = 0.0
            ot = 0.0
            for wd in slip.worked_days_line_ids:
                if wd.code == "LAT":
                    lat += wd.number_of_hours or 0.0
                elif wd.code in ("OTW", "OTR", "PHO"):
                    ot += wd.number_of_hours or 0.0

           # Convert remaining annual leave days to hours (fallback 8 if missing)
hours_per_day = slip.employee_id.resource_calendar_id.hours_per_day if slip.employee_id.resource_calendar_id else 8.0

remaining_leave_days = slip._get_employee_annual_leave_days_safe(slip.employee_id)
leave_hours = remaining_leave_days * hours_per_day

slip.lateness_hours = lat
slip.ot_total_hours = ot
slip.annual_leave_hours = leave_hours

   def _get_employee_annual_leave_days_safe(self, employee):
    """
    Odoo 19 safe: remaining annual leave is not a stored field on hr.employee.
    We try multiple safe ways, and fallback to 0.0 if anything fails.
    """
    # 1) Try standard remaining leaves helper (if available in your build)
    try:
        data = employee._get_remaining_leaves()
        # common patterns in different builds:
        if isinstance(data, dict):
            emp_data = data.get(employee.id) or {}
            for key in ("remaining_leaves", "remaining", "remaining_days", "virtual_remaining_leaves"):
                if key in emp_data and emp_data[key] is not None:
                    return float(emp_data[key])
    except Exception:
        pass

    # 2) Try allocation helper (some builds expose it differently)
    try:
        # Some versions expose a computed method on employee for a specific leave type;
        # if not present it will raise and we fallback.
        return float(getattr(employee, "remaining_leaves", 0.0) or 0.0)
    except Exception:
        return 0.0

    def action_reconcile_lateness(self):
        """Single-click reconciliation:
        - Add this payslip's approved OT hours (OTW/OTR/PHO) to employee OT bank
        - Use OT bank hours first to cover lateness
        - Then use Annual Leave hours (visibility only; does not create a leave request)
        - Remaining lateness hours are stored in 'Remaining (Hours)' for downstream payroll deduction rules
        """
        for slip in self:
            # Safety checks
            if slip.state not in ("draft", "verify"):
                raise UserError(_("Reconciliation is only allowed in Draft or Waiting states."))

            slip._compute_recon_dashboard()

            bank = slip.employee_id.overtime_bank_hours or 0.0

            # Step 0: bank the approved OT hours for this period
            bank += (slip.ot_total_hours or 0.0)

            lateness = slip.lateness_hours or 0.0
            remaining = lateness

            # Step 1: OT bank first
            ot_used = min(remaining, bank)
            bank -= ot_used
            remaining -= ot_used

            # Step 2: Annual leave next (hours)
            leave_avail = slip.annual_leave_hours or 0.0
            leave_used = min(remaining, leave_avail)
            remaining -= leave_used

            # Step 3: store remaining lateness hours (will be salary deduction)
            slip.write({
                "remaining_after_reconciliation_hours": remaining,
                "recon_ot_used_hours": ot_used,
                "recon_leave_used_hours": leave_used,
                "reconciliation_state": "reconciled",
                "reconciliation_date": fields.Datetime.now(),
            })

            # Persist updated OT bank on employee
            slip.employee_id.sudo().write({"overtime_bank_hours": bank})

            # Recompute sheet so any salary rules that read these fields reflect immediately
            slip.compute_sheet()
