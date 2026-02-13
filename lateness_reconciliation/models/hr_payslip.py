from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Dashboard fields (stored computed so they show in list views efficiently)
    dashboard_lateness_hours = fields.Float(
        string="Lateness (hrs)",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )
    dashboard_ot_hours = fields.Float(
        string="Overtime (hrs)",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )
    # Kept for backward compatibility (but not shown in view anymore)
    dashboard_ot_bank = fields.Float(
        string="OT Bank (hrs)",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )
    dashboard_remaining = fields.Float(
        string="Remaining (hrs)",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )

    # Legacy safe fields (kept for backwards compatibility with any existing views/rules)
    lateness_hours = fields.Float(
        string="Lateness Hours",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )
    ot_hours_total = fields.Float(
        string="OT Hours (Total)",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )
    ot_bank_hours = fields.Float(
        string="OT Bank Hours",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )
    lateness_remaining = fields.Float(
        string="Lateness Remaining",
        compute="_compute_dashboard_fields",
        store=True,
        readonly=True,
    )

    # --- CONFIG (codes) ---
    # Lateness codes in worked days lines
    _LATENESS_CODES = ("LAT", "LATE")
    # Overtime codes in worked days lines (priority for deduction)
    _OT_WEEKEND_CODE = "OTR"
    _OT_HOLIDAY_CODE = "PHO"
    _OT_WEEKDAY_CODE = "OTW"

    @api.depends(
        "worked_days_line_ids.code",
        "worked_days_line_ids.number_of_hours",
        "employee_id",
    )
    def _compute_dashboard_fields(self):
        """Compute lateness/OT metrics from worked days lines.

        Expected worked days codes:
          - LAT / LATE : lateness hours
          - OTW / OTR / PHO : overtime hours
        Remaining (hrs) = current lateness hours after reconciliation (what will hit salary deduction).
        """
        for slip in self:
            lateness = 0.0
            overtime = 0.0

            for line in slip.worked_days_line_ids:
                code = (line.code or "").strip()
                if code in self._LATENESS_CODES:
                    lateness += line.number_of_hours or 0.0
                elif code in (self._OT_WEEKDAY_CODE, self._OT_WEEKEND_CODE, self._OT_HOLIDAY_CODE):
                    overtime += line.number_of_hours or 0.0

            # OT Bank is no longer used; keep as 0 for compatibility
            ot_bank = 0.0
            remaining = max(lateness, 0.0)

            slip.dashboard_lateness_hours = lateness
            slip.dashboard_ot_hours = overtime
            slip.dashboard_ot_bank = ot_bank
            slip.dashboard_remaining = remaining

            slip.lateness_hours = lateness
            slip.ot_hours_total = overtime
            slip.ot_bank_hours = ot_bank
            slip.lateness_remaining = remaining

    def _deduct_hours_from_worked_days(self, slip, codes_priority, hours_to_deduct):
        """Deduct hours from worked days lines (in-place) following code priority.

        Returns: deducted_hours (float)
        """
        remaining = hours_to_deduct
        deducted = 0.0

        for code in codes_priority:
            if remaining <= 0:
                break

            lines = slip.worked_days_line_ids.filtered(lambda l: (l.code or '').strip() == code)
            for line in lines:
                if remaining <= 0:
                    break
                available = line.number_of_hours or 0.0
                if available <= 0:
                    continue
                use = min(available, remaining)
                line.number_of_hours = available - use
                remaining -= use
                deducted += use

        return deducted

    def _create_and_validate_annual_leave_hours(self, employee, date_from, hours, leave_type=None):
        """Create & validate an Annual Leave (hours) request to consume balance.

        Returns: hr.leave record (or False if cannot create)
        """
        if hours <= 0:
            return False

        LeaveType = self.env["hr.leave.type"]
        Leave = self.env["hr.leave"]

        if not leave_type:
            # Prefer exact, then fallback to 'Annual'
            leave_type = LeaveType.search([("name", "=", "Annual Leave")], limit=1)
            if not leave_type:
                leave_type = LeaveType.search([("name", "ilike", "Annual")], limit=1)

        if not leave_type:
            return False

        # Most lateness will be small; keep within one day window.
        # If ever needed, you can extend this to split across days.
        hour_from = 8.0
        hour_to = min(24.0, hour_from + hours)

        vals = {
            "name": _("Auto Lateness Reconciliation"),
            "employee_id": employee.id,
            "holiday_status_id": leave_type.id,
            "request_date_from": date_from,
            "request_date_to": date_from,
            "request_unit_hours": True,
            "request_hour_from": hour_from,
            "request_hour_to": hour_to,
        }

        leave = Leave.create(vals)

        # Try to validate automatically (depends on Time Off settings/rights)
        try:
            if hasattr(leave, "action_approve"):
                leave.action_approve()
            if hasattr(leave, "action_validate"):
                leave.action_validate()
        except Exception:
            # Leave created but not validated; still returns record for traceability
            pass

        return leave

    def _lateness_reconcile_for_slip(self):
        """Reconcile lateness for a draft payslip:
        1) Deduct from overtime worked days lines in priority:
           Weekend (OTR) -> Holiday (PHO) -> Weekdays (OTW)
        2) If overtime is not enough, deduct from Annual Leave balance (create Time Off in hours)
        3) Remaining lateness stays on LAT line -> will be deducted from salary via payroll rules.
        """
        for slip in self:
            if slip.state != "draft":
                continue

            employee = slip.employee_id
            if not employee:
                continue

            lat_line = slip.worked_days_line_ids.filtered(lambda l: (l.code or '').strip() in self._LATENESS_CODES)[:1]
            if not lat_line:
                continue

            lateness = lat_line.number_of_hours or 0.0
            if lateness <= 0:
                continue

            # 1) Deduct from overtime buckets with strict priority
            ot_priority = (self._OT_WEEKEND_CODE, self._OT_HOLIDAY_CODE, self._OT_WEEKDAY_CODE)
            ot_deducted = self._deduct_hours_from_worked_days(slip, ot_priority, lateness)

            remaining_after_ot = lateness - ot_deducted

            annual_deducted = 0.0
            leave_rec = False

            # 2) Deduct from Annual Leave (hours) if overtime not enough
            if remaining_after_ot > 0:
                try:
                    leave_rec = self._create_and_validate_annual_leave_hours(
                        employee=employee,
                        date_from=slip.date_from,
                        hours=remaining_after_ot,
                    )
                    if leave_rec:
                        annual_deducted = remaining_after_ot
                    else:
                        # No annual leave type found
                        annual_deducted = 0.0
                except Exception:
                    annual_deducted = 0.0
                    leave_rec = False

            # Apply reductions to lateness line ONLY for what was actually covered
            covered = ot_deducted + annual_deducted
            new_lateness = max(lateness - covered, 0.0)
            lat_line.number_of_hours = new_lateness

            # Optional audit message in chatter
            try:
                msg = _("Lateness reconciliation: OT used %(ot)s hrs, Annual used %(al)s hrs, Remaining %(rem)s hrs.") % {
                    "ot": round(ot_deducted, 2),
                    "al": round(annual_deducted, 2),
                    "rem": round(new_lateness, 2),
                }
                if leave_rec:
                    msg += _(" Annual Leave: %s") % (leave_rec.display_name,)
                slip.message_post(body=msg)
            except Exception:
                pass

            # Ensure dashboard recompute immediately
            slip._compute_dashboard_fields()

    def _recompute_dashboard_fields(self):
        """Backward-compatible wrapper used by older button logic."""
        self._compute_dashboard_fields()

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    total_lateness = fields.Float(compute="_compute_totals")
    total_overtime = fields.Float(compute="_compute_totals")
    total_remaining = fields.Float(compute="_compute_totals")
    coverage_pct = fields.Float(compute="_compute_totals")

    @api.depends(
        "slip_ids.lateness_hours",
        "slip_ids.ot_hours_total",
        "slip_ids.lateness_remaining",
    )
    def _compute_totals(self):
        for run in self:
            slips = run.slip_ids
            total_lateness = sum(slips.mapped("lateness_hours"))
            total_overtime = sum(slips.mapped("ot_hours_total"))
            total_remaining = sum(slips.mapped("lateness_remaining"))

            run.total_lateness = total_lateness
            run.total_overtime = total_overtime
            run.total_remaining = total_remaining

            if total_lateness > 0:
                run.coverage_pct = ((total_lateness - total_remaining) / total_lateness) * 100
            else:
                run.coverage_pct = 100.0

    def action_mass_reconcile_lateness_enterprise(self):
        """Mass reconcile action that works from:
        - Pay Run (hr.payslip.run) form action
        - Payslips list action (active_ids = payslips)
        """
        active_model = self.env.context.get("active_model")
        active_ids = self.env.context.get("active_ids", [])

        slips = self.env["hr.payslip"]

        if active_model == "hr.payslip" and active_ids:
            slips = slips.browse(active_ids)
        else:
            # Called from Pay Run form
            slips = self.slip_ids

        if not slips:
            raise UserError(_("No payslips found to reconcile."))

        slips = slips.filtered(lambda s: s.state == "draft")

        for slip in slips:
            if hasattr(slip, "_lateness_reconcile_for_slip"):
                slip._lateness_reconcile_for_slip()

        slips._recompute_dashboard_fields()

        return {"type": "ir.actions.client", "tag": "reload"}
