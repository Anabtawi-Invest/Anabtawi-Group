# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Dashboard fields (computed from worked days lines)
    pce_ot_total_hours = fields.Float(string="OT Total (Hours)", compute="_compute_pce_metrics", store=True)
    pce_lateness_hours = fields.Float(string="Lateness (Hours)", compute="_compute_pce_metrics", store=True)
    pce_annual_available_hours = fields.Float(string="Annual Leave (Hours)", compute="_compute_pce_metrics", store=True)

    # Results after reconciliation
    pce_ot_used_hours = fields.Float(string="OT Used (Hours)", default=0.0, copy=False, readonly=True)
    pce_annual_used_hours = fields.Float(string="Annual Used (Hours)", default=0.0, copy=False, readonly=True)
    pce_remaining_hours = fields.Float(string="Remaining (Hours)", default=0.0, copy=False, readonly=True)

    # Button tracking + idempotency
    pce_reconciled = fields.Boolean(string="Reconciled", default=False, copy=False, readonly=True)
    pce_reconciled_on = fields.Datetime(string="Reconciled On", copy=False, readonly=True)
    pce_bank_delta_hours = fields.Float(string="OT Bank Delta (Hours)", default=0.0, copy=False, readonly=True)

    # helpful IDs in list
    employee_identification_id = fields.Char(related="employee_id.identification_id", string="ID Number", readonly=True, store=True)
    employee_barcode = fields.Char(related="employee_id.barcode", string="Employee No.", readonly=True, store=True)

    # -------------------------
    # Odoo 19 SAFE annual remaining days
    # NOTE: This returns overall remaining leaves, not a specific leave type.
    # If you want ONLY Annual Leave, we can filter by leave type later.
    # -------------------------
    def _pce_get_remaining_leave_days_safe(self, employee):
        try:
            data = employee._get_remaining_leaves()
            if isinstance(data, dict):
                emp_data = data.get(employee.id) or {}
                val = emp_data.get("remaining_leaves")
                return float(val or 0.0) if val is not None else 0.0
        except Exception:
            return 0.0
        return 0.0

    @api.depends("worked_days_line_ids.number_of_hours", "worked_days_line_ids.code", "employee_id.resource_calendar_id")
    def _compute_pce_metrics(self):
        for slip in self:
            ot = 0.0
            lat = 0.0
            for wd in slip.worked_days_line_ids:
                if wd.code == "LAT":
                    lat += wd.number_of_hours or 0.0
                elif wd.code in ("OTW", "OTR", "PHO"):
                    ot += wd.number_of_hours or 0.0

            hours_per_day = slip.employee_id.resource_calendar_id.hours_per_day if slip.employee_id.resource_calendar_id else 8.0
            annual_days = slip._pce_get_remaining_leave_days_safe(slip.employee_id)
            annual_hours = annual_days * hours_per_day

            slip.pce_ot_total_hours = ot
            slip.pce_lateness_hours = lat
            slip.pce_annual_available_hours = annual_hours

    # -------------------------
    # Salary input automation (keeps standard payroll)
    # -------------------------
    def _pce_write_salary_input_hours(self, input_code, hours):
        self.ensure_one()
        InputType = self.env["hr.payslip.input.type"].sudo()
        input_type = InputType.search([("code", "=", input_code)], limit=1)
        if not input_type:
            return

        existing = self.input_line_ids.filtered(lambda l: l.input_type_id.id == input_type.id).sudo()

        if (hours or 0.0) <= 0:
            if existing:
                existing.unlink()
            return

        vals = {
            "name": input_type.name,
            "input_type_id": input_type.id,
            "amount": float(hours),
            "payslip_id": self.id,
        }
        if existing:
            existing.write(vals)
        else:
            self.env["hr.payslip.input"].sudo().create(vals)

    # -------------------------
    # Button action: reconcile
    # -------------------------
    def action_pce_reconcile(self):
        for slip in self:
            slip._pce_reconcile_one()
        return True

    def _pce_reconcile_one(self):
        self.ensure_one()
        if self.state not in ("draft", "verify"):
            raise UserError(_("Reconciliation is allowed only in Draft or Waiting states."))

        self._compute_pce_metrics()
        employee = self.employee_id.sudo()

        # revert old delta if previously reconciled (prevents OT bank double counting)
        current_bank = employee.overtime_bank_hours or 0.0
        old_delta = self.pce_bank_delta_hours or 0.0
        if self.pce_reconciled and old_delta:
            current_bank -= old_delta

        approved_ot = self.pce_ot_total_hours or 0.0
        lateness = self.pce_lateness_hours or 0.0

        # Step A: bank OT for this period (unpaid)
        bank_after_banking = current_bank + approved_ot

        # Step B: OT bank offsets lateness first
        remaining = lateness
        ot_used = min(remaining, bank_after_banking)
        bank_after_ot = bank_after_banking - ot_used
        remaining -= ot_used

        # Step C: Annual Leave offsets next (tracking only)
        annual_avail = self.pce_annual_available_hours or 0.0
        annual_used = min(remaining, annual_avail)
        remaining -= annual_used

        # Step D: remaining becomes salary deduction HOURS via salary input
        salary_deduct_hours = remaining

        # net delta applied to employee bank
        new_delta = bank_after_ot - current_bank  # == approved_ot - ot_used

        # write results
        self.write({
            "pce_ot_used_hours": ot_used,
            "pce_annual_used_hours": annual_used,
            "pce_remaining_hours": salary_deduct_hours,
            "pce_bank_delta_hours": new_delta,
            "pce_reconciled": True,
            "pce_reconciled_on": fields.Datetime.now(),
        })

        # update employee bank
        employee.write({"overtime_bank_hours": current_bank + new_delta})

        # AUTO salary input hours (your standard salary rule uses inputs.LAT_SAL_DED)
        self._pce_write_salary_input_hours("LAT_SAL_DED", salary_deduct_hours)

        # refresh payslip computation
        self.compute_sheet()
