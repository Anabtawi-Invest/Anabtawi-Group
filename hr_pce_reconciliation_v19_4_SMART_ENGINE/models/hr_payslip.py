from odoo import models, fields, api, _
from odoo.exceptions import UserError

OT_CODES = {"OTW", "OTR", "PHO"}
LAT_CODE = "LAT"
LAT_INPUT_CODE = "LAT_SAL_DED"

def _safe_hours(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Dashboard (computed from worked days lines)
    lateness_hours = fields.Float(string="Lateness (Hours)", compute="_compute_pce_dashboard", store=True, readonly=True)
    ot_weekdays_hours = fields.Float(string="OT Weekdays (Hours)", compute="_compute_pce_dashboard", store=True, readonly=True)
    ot_weekend_hours = fields.Float(string="OT Weekend (Hours)", compute="_compute_pce_dashboard", store=True, readonly=True)
    ot_holiday_hours = fields.Float(string="OT Holiday (Hours)", compute="_compute_pce_dashboard", store=True, readonly=True)
    ot_total_hours = fields.Float(string="OT Total (Hours)", compute="_compute_pce_dashboard", store=True, readonly=True)
    annual_leave_hours = fields.Float(string="Annual Leave Available (Hours)", compute="_compute_pce_dashboard", store=True, readonly=True)

    # Reconciliation results
    pce_bank_before_hours = fields.Float(string="OT Bank Before (Hours)", readonly=True)
    pce_bank_after_hours = fields.Float(string="OT Bank After (Hours)", readonly=True)

    recon_ot_used_hours = fields.Float(string="OT Used (Hours)", readonly=True)
    recon_leave_used_hours = fields.Float(string="Leave Used (Hours)", readonly=True)
    remaining_after_reconciliation_hours = fields.Float(string="Remaining (Hours)", readonly=True)

    reconciliation_state = fields.Selection(
        [("draft", "Draft"), ("done", "Done")],
        default="draft",
        readonly=True,
    )
    reconciliation_date = fields.Datetime(readonly=True)

    # ---------- Annual Leave balance (safe) ----------
    def _pce_get_annual_leave_type(self):
        LeaveType = self.env["hr.leave.type"].sudo()
        lt = LeaveType.search([("name", "ilike", "annual")], limit=1)
        if not lt:
            lt = LeaveType.search([("name", "ilike", "سنوي")], limit=1)
        if not lt:
            lt = LeaveType.search([("requires_allocation", "=", "yes")], limit=1)
        return lt

    def _pce_get_leave_balance_hours(self, employee):
        if not employee:
            return 0.0
        lt = self._pce_get_annual_leave_type()
        if not lt:
            return 0.0

        Allocation = self.env["hr.leave.allocation"].sudo()
        Leave = self.env["hr.leave"].sudo()

        alloc_days = sum(Allocation.search([
            ("employee_id", "=", employee.id),
            ("holiday_status_id", "=", lt.id),
            ("state", "=", "validate"),
        ]).mapped("number_of_days"))

        taken_days = sum(Leave.search([
            ("employee_id", "=", employee.id),
            ("holiday_status_id", "=", lt.id),
            ("state", "=", "validate"),
        ]).mapped("number_of_days"))

        remaining_days = max(0.0, alloc_days - taken_days)

        hours_per_day = 8.0
        cal = employee.resource_calendar_id
        if cal and cal.hours_per_day:
            hours_per_day = cal.hours_per_day
        return remaining_days * hours_per_day

    # ---------- Dashboard compute ----------
    @api.depends("worked_days_line_ids", "employee_id", "employee_id.resource_calendar_id")
    def _compute_pce_dashboard(self):
        for slip in self:
            otw = otr = pho = lat = 0.0
            for line in slip.worked_days_line_ids:
                code = (line.code or "").strip()
                if code == "OTW":
                    otw += _safe_hours(line.number_of_hours)
                elif code == "OTR":
                    otr += _safe_hours(line.number_of_hours)
                elif code == "PHO":
                    pho += _safe_hours(line.number_of_hours)
                elif code == LAT_CODE:
                    lat += _safe_hours(line.number_of_hours)

            slip.ot_weekdays_hours = otw
            slip.ot_weekend_hours = otr
            slip.ot_holiday_hours = pho
            slip.ot_total_hours = otw + otr + pho
            slip.lateness_hours = lat
            slip.annual_leave_hours = slip._pce_get_leave_balance_hours(slip.employee_id)

    # ---------- Salary input writer ----------
    def _pce_set_lateness_input_hours(self, hours):
        self.ensure_one()
        hours = max(0.0, _safe_hours(hours))

        input_type = self.env["hr.payslip.input.type"].search([("code", "=", LAT_INPUT_CODE)], limit=1)
        if not input_type:
            raise UserError(_("Missing Salary Input Type with code %s. Create it in Payroll > Configuration > Salary Input Types.") % LAT_INPUT_CODE)

        line = self.input_line_ids.filtered(lambda l: l.input_type_id.id == input_type.id)[:1]
        if line:
            line.amount = hours
        else:
            self.write({"input_line_ids": [(0, 0, {"input_type_id": input_type.id, "amount": hours})]})

    # ---------- Button action ----------
    def action_reconcile_lateness(self):
        for slip in self:
            if not slip.employee_id:
                continue

            bank_before = _safe_hours(slip.employee_id.pce_ot_bank_hours)
            current_ot = _safe_hours(slip.ot_total_hours)
            lateness = _safe_hours(slip.lateness_hours)
            leave_avail = _safe_hours(slip.annual_leave_hours)

            available_ot = bank_before + current_ot
            remaining = lateness
            ot_used = 0.0
            leave_used = 0.0

            # Step 1: OT (bank + current month)
            if remaining > 0 and available_ot > 0:
                ot_used = min(remaining, available_ot)
                remaining -= ot_used

            bank_after = max(0.0, available_ot - ot_used)

            # Step 2: Annual Leave
            if remaining > 0 and leave_avail > 0:
                leave_used = min(remaining, leave_avail)
                remaining -= leave_used

            # Step 3: Remaining -> Salary Input (hours)
            slip._pce_set_lateness_input_hours(remaining)

            slip.pce_bank_before_hours = bank_before
            slip.pce_bank_after_hours = bank_after
            slip.recon_ot_used_hours = ot_used
            slip.recon_leave_used_hours = leave_used
            slip.remaining_after_reconciliation_hours = remaining
            slip.reconciliation_state = "done"
            slip.reconciliation_date = fields.Datetime.now()

            slip.employee_id.sudo().write({"pce_ot_bank_hours": bank_after})

        return True
