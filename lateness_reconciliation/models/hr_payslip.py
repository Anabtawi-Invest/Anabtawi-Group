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
        "employee_id",
        "employee_id.ot_hours_bank",
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
                if line.code == "LAT":
                    lateness += line.number_of_hours or 0.0
                elif line.code in ("OTW", "OTR", "PHO"):
                    overtime += line.number_of_hours or 0.0

            # Safe access (field is provided by this module, but guard anyway)
            ot_bank = slip.employee_id.ot_hours_bank if slip.employee_id else 0.0
            ot_bank = ot_bank or 0.0

            remaining = lateness - ot_bank
            if remaining < 0:
                remaining = 0.0

            slip.dashboard_lateness_hours = lateness
            slip.dashboard_ot_hours = overtime
            slip.dashboard_ot_bank = ot_bank
            slip.dashboard_remaining = remaining

            slip.lateness_hours = lateness
            slip.ot_hours_total = overtime
            slip.ot_bank_hours = ot_bank
            slip.lateness_remaining = remaining

    def _lateness_reconcile_for_slip(self):
        """Consume employee OT bank to cover lateness on a draft payslip.

        Behavior:
          - Find worked days line with code 'LAT'
          - Reduce its number_of_hours by coverage amount
          - Deduct the same amount from employee_id.ot_hours_bank

        Notes:
          - Only intended for DRAFT payslips.
          - Does not create extra lines; it adjusts the LAT line directly.
        """
        for slip in self:
            if slip.state != "draft":
                continue

            employee = slip.employee_id
            if not employee:
                continue

            ot_bank = employee.ot_hours_bank or 0.0
            if ot_bank <= 0:
                continue

            lat_line = slip.worked_days_line_ids.filtered(lambda l: l.code == "LAT")[:1]
            if not lat_line:
                continue

            lateness = lat_line.number_of_hours or 0.0
            if lateness <= 0:
                continue

            cover = min(lateness, ot_bank)
            # Reduce lateness on slip
            lat_line.number_of_hours = lateness - cover
            # Reduce employee bank
            employee.ot_hours_bank = ot_bank - cover

    def _recompute_dashboard_fields(self):
        """Backward-compatible wrapper used by older button logic."""
        self._compute_dashboard_fields()
