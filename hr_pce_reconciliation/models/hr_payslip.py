# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    pce_reconciled = fields.Boolean(string="PCE Reconciled", default=False, copy=False)
    pce_reconciled_on = fields.Datetime(string="PCE Reconciled On", copy=False)
    pce_reconciled_by = fields.Many2one("res.users", string="PCE Reconciled By", copy=False)

    pce_ot_hours_total = fields.Float(string="OT Hours (Total)", compute="_compute_pce_metrics", store=True)
    pce_lateness_hours = fields.Float(string="Lateness (Hours)", compute="_compute_pce_metrics", store=True)

    pce_annual_hours_used = fields.Float(string="Annual Used (Hours)", copy=False)
    pce_salary_hours_deducted = fields.Float(string="Salary Deducted (Hours)", copy=False)

    @api.depends("input_line_ids.amount", "input_line_ids.input_type_id.code")
    def _compute_pce_metrics(self):
        for slip in self:
            otw = slip._pce_get_input_hours("OTW_H")
            otr = slip._pce_get_input_hours("OTR_H")
            pho = slip._pce_get_input_hours("PHO_H")
            lat = slip._pce_get_input_hours("LAT_H")
            slip.pce_ot_hours_total = otw + otr + pho
            slip.pce_lateness_hours = lat

    def _pce_get_input_hours(self, code):
        self.ensure_one()
        line = self.input_line_ids.filtered(lambda l: l.input_type_id.code == code)[:1]
        return float(line.amount or 0.0) if line else 0.0

    def _pce_find_annual_leave_type(self):
        LeaveType = self.env["hr.leave.type"].sudo()
        lt = LeaveType.search([("name", "ilike", "annual")], limit=1)
        if not lt:
            lt = LeaveType.search([("name", "ilike", "year")], limit=1)
        if not lt:
            lt = LeaveType.search([], limit=1)
        if not lt:
            raise UserError(_("No Time Off Type found. Please create an Annual Leave type in Time Off."))
        return lt

    def _pce_apply_annual_leave_hours(self, hours):
        self.ensure_one()
        if hours <= 0:
            return False

        leave_type = self._pce_find_annual_leave_type()

        # Create an hours-based leave request on the payslip start date.
        leave = self.env["hr.leave"].sudo().create({
            "name": _("Payroll Lateness Reconciliation (%s)") % (self.name or ""),
            "holiday_status_id": leave_type.id,
            "employee_id": self.employee_id.id,
            "request_date_from": self.date_from.date(),
            "request_date_to": self.date_from.date(),
            "request_unit_hours": True,
            "request_hour_from": 0.0,
            "request_hour_to": 0.0,
            "number_of_hours_display": hours,
        })
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

    def action_pce_reconcile(self):
        for slip in self:
            slip._pce_reconcile_one()
        return True

    def _pce_reconcile_one(self):
        self.ensure_one()
        if self.pce_reconciled:
            raise UserError(_("This payslip is already reconciled."))

        ot_total = self._pce_get_input_hours("OTW_H") + self._pce_get_input_hours("OTR_H") + self._pce_get_input_hours("PHO_H")
        lat = self._pce_get_input_hours("LAT_H")

        remaining = max(0.0, lat - ot_total)
        annual_used = 0.0
        salary_deduct = 0.0

        if remaining > 0:
            annual_used = remaining
            try:
                self._pce_apply_annual_leave_hours(annual_used)
                remaining = 0.0
            except Exception:
                # If Time Off isn't configured or validation fails, move remaining to salary
                salary_deduct = remaining
                remaining = 0.0

        self._pce_mark_lateness_work_entries_reconciled()

        # Compute + finalize payslip (and accounting move if configured)
        if self.state in ("draft", "verify"):
            self.compute_sheet()
        if self.state not in ("done", "paid"):
            try:
                self.action_payslip_done()
            except Exception:
                pass

        self.write({
            "pce_reconciled": True,
            "pce_reconciled_on": fields.Datetime.now(),
            "pce_reconciled_by": self.env.user.id,
            "pce_annual_hours_used": annual_used,
            "pce_salary_hours_deducted": salary_deduct,
        })

        self.message_post(body=_(
            "PCE Reconciled.<br/>"
            "OT Hours: %s<br/>"
            "Lateness Hours: %s<br/>"
            "Annual Used (Hours): %s<br/>"
            "Salary Deducted (Hours): %s"
        ) % (ot_total, lat, annual_used, salary_deduct))

        return True
