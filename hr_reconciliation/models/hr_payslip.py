from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    lateness_hours = fields.Float(compute="_compute_recon_dashboard", store=True)
    ot_total_hours = fields.Float(compute="_compute_recon_dashboard", store=True)
    annual_leave_hours = fields.Float(compute="_compute_recon_dashboard", store=True)

    remaining_after_reconciliation_hours = fields.Float()
    recon_ot_used_hours = fields.Float()
    recon_leave_used_hours = fields.Float()

    # =====================================================
    # SAFE ANNUAL LEAVE READER (ODOO 19)
    # =====================================================

    def _get_employee_annual_leave_days_safe(self, employee):
        try:
            data = employee._get_remaining_leaves()
            if isinstance(data, dict):
                emp_data = data.get(employee.id, {})
                return float(emp_data.get('remaining_leaves', 0.0))
        except Exception:
            pass
        return 0.0

    # =====================================================
    # COMPUTE DASHBOARD
    # =====================================================

    @api.depends(
        "worked_days_line_ids.number_of_hours",
        "worked_days_line_ids.code",
        "employee_id.resource_calendar_id"
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

    # =====================================================
    # RECONCILIATION BUTTON
    # =====================================================

    def action_reconcile_lateness(self):
        for slip in self:

            if slip.state not in ("draft", "verify"):
                raise UserError(_("Reconciliation allowed only in Draft or Waiting."))

            slip._compute_recon_dashboard()

            bank = slip.employee_id.overtime_bank_hours or 0.0
            bank += slip.ot_total_hours or 0.0

            lateness = slip.lateness_hours or 0.0
            remaining = lateness

            ot_used = min(remaining, bank)
            bank -= ot_used
            remaining -= ot_used

            leave_avail = slip.annual_leave_hours or 0.0
            leave_used = min(remaining, leave_avail)
            remaining -= leave_used

            slip.remaining_after_reconciliation_hours = remaining
            slip.recon_ot_used_hours = ot_used
            slip.recon_leave_used_hours = leave_used

            slip.employee_id.sudo().write({
                "overtime_bank_hours": bank
            })

            slip.compute_sheet()
