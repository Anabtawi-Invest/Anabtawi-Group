from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Display fields (no naming)
    lateness_hours = fields.Float(
        string="Lateness (hrs)",
        compute="_compute_lateness_overtime",
        store=True,
        readonly=True,
    )
    overtime_hours = fields.Float(
        string="Overtime (hrs)",
        compute="_compute_lateness_overtime",
        store=True,
        readonly=True,
    )

    covered_by_overtime_hours = fields.Float(
        string="Covered by OT (hrs)",
        readonly=True,
        copy=False,
        default=0.0,
    )
    covered_by_annual_leave_hours = fields.Float(
        string="Covered by Annual Leave (hrs)",
        readonly=True,
        copy=False,
        default=0.0,
    )

    remaining_lateness_hours = fields.Float(
        string="Remaining Lateness (hrs)",
        compute="_compute_remaining_lateness",
        store=True,
        readonly=True,
    )

    @api.depends("worked_days_line_ids.code", "worked_days_line_ids.number_of_hours")
    def _compute_lateness_overtime(self):
        """Compute lateness + overtime totals from worked days lines.

        Expected codes:
          - Lateness: LAT or LATE
          - Overtime buckets: OTR (Weekend), PHO (Public Holiday), OTW (Weekday)
        """
        for slip in self:
            lateness = 0.0
            overtime = 0.0
            for line in slip.worked_days_line_ids:
                code = (line.code or "").strip()
                hrs = line.number_of_hours or 0.0
                if code in ("LAT", "LATE"):
                    lateness += hrs
                elif code in ("OTR", "PHO", "OTW"):
                    overtime += hrs
            slip.lateness_hours = lateness
            slip.overtime_hours = overtime

    @api.depends("lateness_hours", "covered_by_overtime_hours", "covered_by_annual_leave_hours")
    def _compute_remaining_lateness(self):
        for slip in self:
            remaining = (slip.lateness_hours or 0.0) - (slip.covered_by_overtime_hours or 0.0) - (slip.covered_by_annual_leave_hours or 0.0)
            slip.remaining_lateness_hours = max(remaining, 0.0)

    # ------------------------
    # Reconciliation utilities
    # ------------------------
    def _get_ot_lines_by_code(self, code):
        self.ensure_one()
        return self.worked_days_line_ids.filtered(lambda l: (l.code or "").strip() == code)

    def _reduce_ot_bucket(self, code, hours_to_consume):
        """Consume hours from OT bucket line(s) by reducing number_of_hours."""
        self.ensure_one()
        if hours_to_consume <= 0:
            return 0.0

        consumed = 0.0
        for line in self._get_ot_lines_by_code(code):
            available = line.number_of_hours or 0.0
            if available <= 0:
                continue
            take = min(available, hours_to_consume - consumed)
            if take <= 0:
                break
            line.number_of_hours = available - take
            consumed += take
            if consumed >= hours_to_consume - 1e-9:
                break
        return consumed

    def _get_annual_leave_type(self):
        """Resolve Annual Leave type (hours-based) from company config, otherwise auto-detect."""
        self.ensure_one()
        company = self.company_id
        leave_type = company.lateness_annual_leave_type_id
        if leave_type:
            return leave_type

        # Auto-detect a reasonable default: first leave type that supports hour requests
        LeaveType = self.env["hr.leave.type"].sudo()
        candidates = LeaveType.search([], order="sequence, id")
        # Try to filter by known hour-request fields (varies by version)
        for lt in candidates:
            if hasattr(lt, "request_unit") and lt.request_unit == "hour":
                return lt
            if hasattr(lt, "request_unit_hours") and lt.request_unit_hours:
                return lt
        return False

    def _get_leave_balance_hours(self, leave_type, employee):
        """Best-effort to get remaining leave balance in hours for an employee."""
        # Many Odoo versions expose hr.leave.type.get_employees_days
        try:
            data = leave_type.get_employees_days([employee.id])
            if isinstance(data, dict) and employee.id in data:
                # Common keys
                for key in ("remaining_leaves", "remaining", "virtual_remaining_leaves"):
                    if key in data[employee.id]:
                        return float(data[employee.id][key] or 0.0)
        except Exception:
            pass

        # Fallback: try employee helper if available
        try:
            if hasattr(employee, "_get_remaining_leaves"):
                return float(employee._get_remaining_leaves(leave_type.id) or 0.0)
        except Exception:
            pass

        return 0.0

    def _create_and_validate_hour_leave(self, leave_type, hours, date_from):
        """Create and validate a Time Off request in HOURS to consume Annual Leave balance."""
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            raise UserError(_("Payslip has no employee."))

        if hours <= 0:
            return False

        # Pick a date within payslip period; use date_from if set, else today in employee tz
        if not date_from:
            date_from = fields.Date.context_today(self)

        # Build a minimal hour-based leave request.
        # Note: Fields differ slightly across versions; we set common ones and rely on Odoo to compute days/hours.
        vals = {
            "name": _("Lateness Coverage (%s hrs)") % hours,
            "holiday_status_id": leave_type.id,
            "employee_id": employee.id,
        }

        # Try hour request fields if present
        HrLeave = self.env["hr.leave"].sudo()

        # date fields are usually required
        if "request_date_from" in HrLeave._fields and "request_date_to" in HrLeave._fields:
            vals["request_date_from"] = date_from
            vals["request_date_to"] = date_from

        # hour request toggles and hour range if supported
        if "request_unit_hours" in HrLeave._fields:
            vals["request_unit_hours"] = True
        if "request_hour_from" in HrLeave._fields and "request_hour_to" in HrLeave._fields:
            vals["request_hour_from"] = 0.0
            vals["request_hour_to"] = float(hours)

        # Some versions use number_of_hours_display
        if "number_of_hours_display" in HrLeave._fields:
            vals["number_of_hours_display"] = float(hours)

        leave = HrLeave.create(vals)

        # Validate / approve (methods vary slightly)
        # We try the typical chain: action_confirm -> action_approve -> action_validate
        for method in ("action_confirm", "action_approve", "action_validate"):
            if hasattr(leave, method):
                getattr(leave, method)()

        return leave

    def _lateness_reconcile_for_slip_no_ot_bank(self):
        """Cover lateness using OT buckets then Annual Leave hours. Leave remaining for salary deduction.

        Priority for OT consumption (must reduce OT hours):
          1) OTR (Weekend OT)
          2) PHO (Holiday OT)
          3) OTW (Weekday OT)
        """
        for slip in self:
            if slip.state != "draft":
                continue

            slip.ensure_one()
            employee = slip.employee_id
            if not employee:
                continue

            L = slip.lateness_hours or 0.0
            if L <= 0:
                # Reset coverage fields if no lateness
                slip.write({
                    "covered_by_overtime_hours": 0.0,
                    "covered_by_annual_leave_hours": 0.0,
                })
                continue

            remaining = L
            covered_ot = 0.0

            # Consume OT buckets in strict priority order
            for code in ("OTR", "PHO", "OTW"):
                if remaining <= 0:
                    break
                consumed = slip._reduce_ot_bucket(code, remaining)
                covered_ot += consumed
                remaining -= consumed

            covered_leave = 0.0
            if remaining > 0:
                leave_type = slip._get_annual_leave_type()
                if not leave_type:
                    raise UserError(_(
                        "Annual Leave type (hours) is not configured. "
                        "Please set it in Settings or create an hour-based Annual Leave type."
                    ))

                available = slip._get_leave_balance_hours(leave_type, employee)
                if available > 0:
                    to_deduct = min(remaining, available)
                    if to_deduct > 0:
                        slip._create_and_validate_hour_leave(
                            leave_type=leave_type,
                            hours=to_deduct,
                            date_from=slip.date_from or slip.date_to,
                        )
                        covered_leave = to_deduct
                        remaining -= to_deduct

            slip.write({
                "covered_by_overtime_hours": covered_ot,
                "covered_by_annual_leave_hours": covered_leave,
            })

            # Recompute display fields (stored computes)
            slip._compute_lateness_overtime()
            slip._compute_remaining_lateness()
