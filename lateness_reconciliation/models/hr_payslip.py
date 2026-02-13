from odoo import models, fields, api

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

    @api.depends(
        "worked_days_line_ids.code",
        "worked_days_line_ids.number_of_hours",
        "employee_id"
    )
    def _compute_dashboard_fields(self):
        """Compute lateness/OT metrics from worked days lines + employee OT bank.

        Expected worked days codes:
          - LAT : lateness hours
          - OTW / OTR / PHO : overtime hours (adapt as needed)
        """
        for slip in self:
            lateness = 0.0
            overtime = 0.0

            for line in slip.worked_days_line_ids:
                if line.code in ("LAT","LATE"):
                    lateness += line.number_of_hours or 0.0
                elif line.code in ("OTW", "OTR", "PHO"):
                    overtime += line.number_of_hours or 0.0

            # Safe access (field is provided by this module, but guard anyway)
            ot_bank = 0.0

            remaining = lateness

            slip.dashboard_lateness_hours = lateness
            slip.dashboard_ot_hours = overtime
            slip.dashboard_ot_bank = ot_bank
            slip.dashboard_remaining = remaining

            slip.lateness_hours = lateness
            slip.ot_hours_total = overtime
            slip.ot_bank_hours = ot_bank
            slip.lateness_remaining = remaining

    
    def _lateness_reconcile_for_slip(self):
        """Reconcile lateness on draft payslips using:
           1) Overtime hours on the SAME payslip (reduce OT pay)
              Priority: OTR (Weekend) -> PHO (Holiday) -> OTW (Weekdays)
           2) If OT doesn't fully cover -> create/validate Annual Leave (hours)
           3) If Annual Leave creation/validation fails -> keep remaining lateness,
              so salary rule LATE_DED can deduct it on Compute Sheet.

        Notes:
          - Works on DRAFT payslips only.
          - Adjusts worked days lines directly (lateness + overtime lines).
        """
        HrLeave = self.env['hr.leave']
        HrLeaveType = self.env['hr.leave.type']

        for slip in self:
            if slip.state != "draft":
                continue

            # Find lateness line
            lat_line = slip.worked_days_line_ids.filtered(lambda l: l.code in ("LAT", "LATE"))[:1]
            if not lat_line:
                continue

            lateness = lat_line.number_of_hours or 0.0
            if lateness <= 0:
                continue

            # Helper: hours per day (used only to keep days field consistent)
            hours_per_day = 8.0
            try:
                cal = slip.employee_id.resource_calendar_id
                if cal and getattr(cal, 'hours_per_day', 0.0):
                    hours_per_day = cal.hours_per_day
            except Exception:
                pass

            remaining = lateness

            # 1) Consume overtime hours (reduce OT pay)
            # Priority: weekend -> holiday -> weekdays
            ot_priority = ("OTR", "PHO", "OTW")
            for code in ot_priority:
                if remaining <= 0:
                    break
                ot_line = slip.worked_days_line_ids.filtered(lambda l: l.code == code)[:1]
                if not ot_line:
                    continue

                ot_hours = ot_line.number_of_hours or 0.0
                if ot_hours <= 0:
                    continue

                consume = min(ot_hours, remaining)
                # reduce OT line hours
                ot_line.number_of_hours = ot_hours - consume
                # keep days aligned if possible
                try:
                    if ot_line.number_of_days is not False and hours_per_day:
                        ot_line.number_of_days = (ot_line.number_of_hours or 0.0) / hours_per_day
                except Exception:
                    pass

                remaining -= consume

            # reduce lateness by OT coverage
            covered_by_ot = lateness - remaining
            if covered_by_ot > 0:
                lat_line.number_of_hours = remaining
                try:
                    if lat_line.number_of_days is not False and hours_per_day:
                        lat_line.number_of_days = (lat_line.number_of_hours or 0.0) / hours_per_day
                except Exception:
                    pass

            # 2) If still remaining, try Annual Leave (hours) - auto approved
            if remaining > 0 and slip.employee_id:
                try:
                    annual_type = HrLeaveType.search([('name', '=', 'Annual Leave')], limit=1)
                    if annual_type:
                        # Create a leave request in hours.
                        # We keep dates within the payslip period (same day request is simplest).
                        # Odoo will compute duration based on hours fields.
                        vals = {
                            'employee_id': slip.employee_id.id,
                            'holiday_status_id': annual_type.id,
                            'name': 'Auto Annual Leave for Lateness (%s)' % (slip.name or ''),
                            # Use payslip start date for the request
                            'request_date_from': slip.date_from,
                            'request_date_to': slip.date_from,
                            'request_unit_hours': True,
                            'request_hour_from': 0.0,
                            'request_hour_to': float(remaining),
                        }
                        leave = HrLeave.sudo().create(vals)
                        # Auto-approve
                        leave.sudo().action_approve()
                        leave.sudo().action_validate()

                        # Annual leave consumed -> clear remaining lateness
                        lat_line.number_of_hours = 0.0
                        try:
                            lat_line.number_of_days = 0.0
                        except Exception:
                            pass
                        remaining = 0.0
                except Exception:
                    # If anything fails, we keep remaining lateness hours.
                    pass

            # recompute stored dashboard fields
            slip._compute_dashboard_fields()

    def action_mass_reconcile_lateness(self):
        """Entry point for Server Action: reconcile selected payslips."""
        self._lateness_reconcile_for_slip()
        return True

    def _recompute_dashboard_fields(self):
        """Backward-compatible wrapper used by older button logic."""
        self._compute_dashboard_fields()
