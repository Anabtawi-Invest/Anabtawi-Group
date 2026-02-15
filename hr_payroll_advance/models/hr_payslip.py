# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Dashboard (read-only compute; no side effects)
    pce_lateness_hours = fields.Float(string="Lateness Hours", compute="_compute_pce_dashboard", store=False)
    pce_ot_hours = fields.Float(string="OT Hours", compute="_compute_pce_dashboard", store=False)
    pce_remaining_lateness_hours = fields.Float(string="Remaining Lateness", compute="_compute_pce_dashboard", store=False)

    # Reconciliation results (stored, written ONLY by action_payslip_done)
    pce_deduct_ot_hours = fields.Float(string="Deducted from OT (Hours)", readonly=True, copy=False)
    pce_deduct_leave_hours = fields.Float(string="Deducted from Annual Leave (Hours)", readonly=True, copy=False)
    pce_unpaid_hours = fields.Float(string="Unpaid Hours (Salary Deduction)", readonly=True, copy=False)
    pce_leave_id = fields.Many2one("hr.leave", string="Created Leave", readonly=True, copy=False)
    pce_reconciliation_applied = fields.Boolean(string="Reconciliation Applied", default=False, readonly=True, copy=False)

    def _pce_set_input(self, code, amount):
        self.ensure_one()
        Input = self.env["hr.payslip.input"]
        line = self.input_line_ids.filtered(lambda l: l.code == code)
        if line:
            line.write({"amount": amount})
        else:
            Input.create({
                "payslip_id": self.id,
                "name": code,
                "code": code,
                "amount": amount,
                "contract_id": self.contract_id.id,
            })

    def _pce_get_param(self, key, default=None):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    def _pce_get_codes(self):
        lateness_code = (self._pce_get_param("pce.lateness_code", "LAT") or "LAT").strip()
        ot_codes = (self._pce_get_param("pce.ot_codes", "OTW,OTR,PHO") or "OTW,OTR,PHO")
        ot_codes = [c.strip() for c in ot_codes.split(",") if c.strip()]
        return lateness_code, ot_codes

    def _compute_pce_dashboard(self):
        for slip in self:
            lateness_code, ot_codes = slip._pce_get_codes()
            lateness = 0.0
            ot = 0.0
            for line in slip.worked_days_line_ids:
                if (line.code or "") == lateness_code:
                    lateness += (line.number_of_hours or 0.0)
                elif (line.code or "") in ot_codes:
                    ot += (line.number_of_hours or 0.0)
            slip.pce_lateness_hours = lateness
            slip.pce_ot_hours = ot
            slip.pce_remaining_lateness_hours = max(lateness - ot, 0.0)

    def _pce_estimate_hourly_rate(self):
        self.ensure_one()
        default_month_hours = float(self._pce_get_param("pce.default_month_hours", "173.33") or 173.33)
        # Prefer regular worked hours line if present
        month_hours = 0.0
        for line in self.worked_days_line_ids:
            # Common codes: WORK100 / WORK / NORMAL; we take the largest non-OT, non-LAT line
            if line.code and line.code not in set(self._pce_get_codes()[1] + [self._pce_get_codes()[0]]):
                month_hours = max(month_hours, line.number_of_hours or 0.0)
        if month_hours <= 0:
            month_hours = default_month_hours
        wage = self.contract_id.wage or 0.0
        return (wage / month_hours) if month_hours else 0.0

    def _pce_create_annual_leave(self, hours):
        self.ensure_one()
        lt_id = int(self._pce_get_param("pce.annual_leave_type_id", "0") or 0)
        if not lt_id:
            return False
        leave_type = self.env["hr.leave.type"].browse(lt_id).exists()
        if not leave_type:
            return False

        # Create an hour-based leave if company uses hours; otherwise create in days with conversion.
        # We keep it robust: use employee's calendar hours_per_day, fallback 8.
        hours_per_day = (self.employee_id.resource_calendar_id.hours_per_day or 8.0) if self.employee_id.resource_calendar_id else 8.0
        days = hours / hours_per_day if hours_per_day else 0.0
        if days <= 0:
            return False

        leave = self.env["hr.leave"].sudo().create({
            "name": _("Auto Annual Leave Deduction (Lateness) - %s") % (self.name or ""),
            "holiday_status_id": leave_type.id,
            "employee_id": self.employee_id.id,
            "request_date_from": self.date_from.date(),
            "request_date_to": self.date_from.date(),
            "request_unit_half": False,
            "request_unit_hours": False,
            "request_unit_custom": False,
            "number_of_days": days,
        })
        # Auto-approve if possible (system-only)
        try:
            leave.action_confirm()
            leave.action_approve()
            if hasattr(leave, "action_validate"):
                leave.action_validate()
        except Exception:
            # If workflow differs, keep it created (HR can validate)
            pass
        return leave

    def action_payslip_done(self):
        res = super().action_payslip_done()
        # Apply once and only once
        for slip in self:
            if slip.pce_reconciliation_applied:
                continue
            if not slip.employee_id or not slip.contract_id:
                continue

            lateness = slip.pce_lateness_hours
            ot = slip.pce_ot_hours
            if lateness <= 0 and ot <= 0:
                slip.write({"pce_reconciliation_applied": True})
                continue

            # 1) Accrue OT hours to bank
            if ot > 0:
                slip.employee_id._pce_post_ot_bank_delta(
                    delta_hours=ot,
                    date=slip.date_to.date(),
                    slip=slip,
                    reference=_("OT Accrual"),
                )

            # Get current bank after accrual
            current_bank = slip.employee_id.ot_bank_balance_hours

            # 2) Consume OT bank for lateness (time-for-time)
            deduct_ot = min(lateness, current_bank) if lateness > 0 else 0.0
            remaining = max(lateness - deduct_ot, 0.0)

            if deduct_ot > 0:
                slip.employee_id._pce_post_ot_bank_delta(
                    delta_hours=-deduct_ot,
                    date=slip.date_to.date(),
                    slip=slip,
                    reference=_("Lateness Offset from OT Bank"),
                )

            # 3) Deduct from Annual Leave (create leave)
            deduct_leave = 0.0
            leave = False
            if remaining > 0:
                # Create leave record for remaining hours; if not configured, leave stays 0 and goes unpaid.
                leave = slip._pce_create_annual_leave(remaining)
                if leave:
                    # Convert created leave back to hours for display
                    hours_per_day = (slip.employee_id.resource_calendar_id.hours_per_day or 8.0) if slip.employee_id.resource_calendar_id else 8.0
                    deduct_leave = (leave.number_of_days or 0.0) * (hours_per_day or 8.0)
                    remaining = max(remaining - deduct_leave, 0.0)

            # 4) Remaining becomes unpaid (salary deduction)
            unpaid = remaining

            # Create/Update payroll input for unpaid hours; included salary rule will convert to money.
            # Input code used by rule: PCE_UNPAID_H
            slip._pce_set_input("PCE_UNPAID_H", unpaid)

            slip.write({
                "pce_deduct_ot_hours": deduct_ot,
                "pce_deduct_leave_hours": deduct_leave,
                "pce_unpaid_hours": unpaid,
                "pce_leave_id": leave.id if leave else False,
                "pce_reconciliation_applied": True,
            })
        return res
