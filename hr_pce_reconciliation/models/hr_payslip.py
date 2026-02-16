# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # =========================================================
    # Reconciliation tracking
    # =========================================================
    pce_reconciled = fields.Boolean(string="PCE Reconciled", default=False, copy=False)
    pce_reconciled_on = fields.Datetime(string="PCE Reconciled On", copy=False)
    pce_reconciled_by = fields.Many2one("res.users", string="PCE Reconciled By", copy=False)

    # =========================================================
    # Dashboard fields (names MUST match views)
    # Values are driven from Inputs + reconciliation results
    # =========================================================
    pce_ot_total_hours = fields.Float(string="OT Total Hours", compute="_compute_pce_metrics", store=True)
    pce_lateness_hours = fields.Float(string="Lateness Hours", compute="_compute_pce_metrics", store=True)

    # These are written at reconciliation time
    pce_annual_used_hours = fields.Float(string="Annual Used Hours", default=0.0, copy=False, readonly=True)
    pce_salary_deduction_hours = fields.Float(string="Salary Deduction Hours", default=0.0, copy=False, readonly=True)

    # Backward-compatible aliases (in case old rules/views referenced them)
    pce_ot_hours_total = fields.Float(related="pce_ot_total_hours", string="OT Hours (Total)", store=True, readonly=True)
    pce_annual_hours_used = fields.Float(related="pce_annual_used_hours", string="Annual Used (Hours)", store=True, readonly=True)
    pce_salary_hours_deducted = fields.Float(related="pce_salary_deduction_hours", string="Salary Deducted (Hours)", store=True, readonly=True)

    # =========================================================
    # Helpers
    # =========================================================
    def _pce_get_input_hours(self, code):
        self.ensure_one()
        line = self.input_line_ids.filtered(lambda l: l.input_type_id.code == code)[:1]
        return float(line.amount or 0.0) if line else 0.0

    @api.depends("input_line_ids.amount", "input_line_ids.input_type_id.code")
    def _compute_pce_metrics(self):
        for slip in self:
            otw = slip._pce_get_input_hours("OTW_H")
            otr = slip._pce_get_input_hours("OTR_H")
            pho = slip._pce_get_input_hours("PHO_H")
            lat = slip._pce_get_input_hours("LAT_H")
            slip.pce_ot_total_hours = otw + otr + pho
            slip.pce_lateness_hours = lat

    def _pce_find_annual_leave_type(self):
        """Pick Annual Leave type safely without hardcoding IDs."""
        LeaveType = self.env["hr.leave.type"].sudo()
        lt = LeaveType.search([("name", "ilike", "annual")], limit=1)
        if not lt:
            lt = LeaveType.search([("name", "ilike", "year")], limit=1)
        if not lt:
            # last resort: any leave type
            lt = LeaveType.search([], limit=1)
        if not lt:
            raise UserError(_("No Time Off Type found. Please create an Annual Leave type in Time Off."))
        return lt

    def _pce_apply_annual_leave_hours(self, hours):
        """Consume annual leave by creating a validated hours-based leave request."""
        self.ensure_one()
        if hours <= 0:
            return False

        leave_type = self._pce_find_annual_leave_type()

        # Request on payslip start date (HR can audit from leave name)
        leave = self.env["hr.leave"].sudo().create({
            "name": _("Payroll Lateness Reconciliation (%s)") % (self.name or ""),
            "holiday_status_id": leave_type.id,
            "employee_id": self.employee_id.id,
            "request_date_from": self.date_from.date(),
            "request_date_to": self.date_from.date(),
            "request_unit_hours": True,
            "number_of_hours_display": hours,
        })
        # Validate with standard workflow
        leave.action_confirm()
        leave.action_approve()
        leave.action_validate()
        return leave

    def _pce_mark_lateness_work_entries_reconciled(self):
        self.ensure_one()
        WorkEntry = self.env["hr.work.entry"].sudo()
        wes = WorkEntry.search([
            ("employee_id", "=", self.employee_id.id),
            ("date_start", ">=", self.date_from),
            ("date_stop", "<=", self.date_to),
            ("work_entry_type_id.code", "=", "LAT"),
        ])
        wes.write({"pce_reconciled": True, "pce_reconciled_payslip_id": self.id})
        return wes

    # =========================================================
    # Actions
    # =========================================================
    def action_pce_reconcile(self):
        for slip in self:
            slip._pce_reconcile_one()
        return True

    def _pce_reconcile_one(self):
        self.ensure_one()
        if self.pce_reconciled:
            raise UserError(_("This payslip is already reconciled."))

        # Inputs drive the reconciliation (stable in Odoo.sh)
        ot_total = self._pce_get_input_hours("OTW_H") + self._pce_get_input_hours("OTR_H") + self._pce_get_input_hours("PHO_H")
        lat = self._pce_get_input_hours("LAT_H")

        # Priority: OT -> Annual -> Salary
        remaining = max(0.0, lat - ot_total)

        annual_used = 0.0
        salary_deduct = 0.0

        if remaining > 0:
            # Try consume annual leave hours
            annual_used = remaining
            try:
                self._pce_apply_annual_leave_hours(annual_used)
                remaining = 0.0
            except Exception:
                # If Time Off isn't configured / validation fails, push remaining to salary
                salary_deduct = remaining
                remaining = 0.0

        # Mark lateness work entries as reconciled
        self._pce_mark_lateness_work_entries_reconciled()

        # Compute + finalize payslip (accounting move is created if payroll accounting configured)
        if self.state in ("draft", "verify"):
            self.compute_sheet()

        if self.state not in ("done", "paid"):
            try:
                self.action_payslip_done()
            except Exception:
                # allow reconcile even if accounting isn't configured yet
                pass

        self.write({
            "pce_reconciled": True,
            "pce_reconciled_on": fields.Datetime.now(),
            "pce_reconciled_by": self.env.user.id,
            "pce_annual_used_hours": annual_used,
            "pce_salary_deduction_hours": salary_deduct,
        })

        self.message_post(body=_(
            "PCE Reconciled.<br/>"
            "OT Total Hours: %s<br/>"
            "Lateness Hours: %s<br/>"
            "Annual Used Hours: %s<br/>"
            "Salary Deduction Hours: %s"
        ) % (ot_total, lat, annual_used, salary_deduct))

        return True
