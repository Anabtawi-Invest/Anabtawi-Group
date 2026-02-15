from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    reconciliation_state = fields.Selection([
        ("pending", "Pending"),
        ("reconciled", "Reconciled"),
    ], default="pending")

    reconciled_at = fields.Datetime()

    late_use_leave = fields.Boolean(string="Use Annual Leave for Lateness", default=False)

    late_leave_id = fields.Many2one("hr.leave", string="Auto Lateness Leave")

    # =====================================================
    # DISPLAY FIELDS
    # =====================================================

    late_hours = fields.Float(
        string="Late Hours",
        compute="_compute_recon_metrics",
        store=True,
    )

    ot_total_amount = fields.Float(
        string="OT Total (Amount)",
        compute="_compute_recon_metrics",
        store=True,
    )

    ot_deduct_hours = fields.Float(
        string="Deduct from OT (Hours)",
        compute="_compute_recon_metrics",
        store=True,
    )

    leave_deduct_hours = fields.Float(
        string="Deduct from Leave (Hours)",
        compute="_compute_recon_metrics",
        store=True,
    )

    salary_deduct_hours = fields.Float(
        string="Salary Deduction (Hours)",
        compute="_compute_recon_metrics",
        store=True,
    )

    leave_hours_available = fields.Float(
        string="Annual Leave Available (Hours)",
        compute="_compute_recon_metrics",
        store=True,
    )

    # =====================================================
    # HELPERS
    # =====================================================

    def _get_annual_leave_type(self):
        return self.env["hr.leave.type"].search([("name", "=", "Annual Leave")], limit=1)

    def _get_hour_rate(self):
        self.ensure_one()
        contract = self.contract_id
        if not contract or not contract.wage:
            return 0.0
        return contract.wage / 240.0

    def _get_late_hours(self):
        total = 0.0
        for w in self.worked_days_line_ids:
            if w.code == "LAT":
                total += w.number_of_hours or 0.0
        return total

    def _get_ot_total_amount(self):
        total = 0.0
        for l in self.line_ids:
            if l.code == "OT_TOTAL":
                total += l.total or 0.0
        return total

    def _get_leave_hours_available(self):
        lt = self._get_annual_leave_type()
        if not lt:
            return 0.0
        data = lt.get_days(self.employee_id.id).get(lt.id, {})
        remaining_days = data.get("remaining_leaves", 0.0) or 0.0
        return remaining_days * 8.0

    # =====================================================
    # COMPUTE ENGINE  (🔥 FIXED DEPENDS)
    # =====================================================

    @api.depends(
        "worked_days_line_ids.number_of_hours",
        "worked_days_line_ids.code",
        "line_ids.total",
        "line_ids.code",
        "late_use_leave"
    )
    def _compute_recon_metrics(self):

        for slip in self:

            late = slip._get_late_hours()
            ot_amount = slip._get_ot_total_amount()
            hr = slip._get_hour_rate()
            leave_avail_h = slip._get_leave_hours_available()

            slip.late_hours = late
            slip.ot_total_amount = ot_amount
            slip.leave_hours_available = leave_avail_h

            ot_cover_h = 0.0
            if hr > 0:
                ot_cover_h = min(late, (ot_amount / hr))

            remaining_after_ot = max(0.0, late - ot_cover_h)

            leave_cover_h = min(remaining_after_ot, leave_avail_h) if slip.late_use_leave else 0.0
            remaining_after_leave = max(0.0, remaining_after_ot - leave_cover_h)

            slip.ot_deduct_hours = ot_cover_h
            slip.leave_deduct_hours = leave_cover_h
            slip.salary_deduct_hours = remaining_after_leave

    # =====================================================
    # RECONCILIATION ENGINE
    # =====================================================

    def action_reconcile_lateness_engine(self):

        for slip in self:

            slip.compute_sheet()

            late = slip._get_late_hours()
            if not late:
                slip.late_use_leave = False
                slip.reconciliation_state = "reconciled"
                slip.reconciled_at = fields.Datetime.now()
                continue

            hr = slip._get_hour_rate()
            ot_amount = slip._get_ot_total_amount()
            leave_avail_h = slip._get_leave_hours_available()

            ot_cover_h = (ot_amount / hr) if hr > 0 else 0.0
            remaining_after_ot = max(0.0, late - ot_cover_h)

            slip.late_use_leave = bool(remaining_after_ot > 0 and leave_avail_h >= 0.01)

            slip.compute_sheet()

            slip.reconciliation_state = "reconciled"
            slip.reconciled_at = fields.Datetime.now()

        return True

    # =====================================================
    # AUTO LEAVE CREATION
    # =====================================================

    def action_payslip_done(self):
        res = super().action_payslip_done()

        for slip in self:

            if not slip.late_use_leave:
                continue

            if slip.late_leave_id:
                continue

            leave_hours = slip.leave_deduct_hours or 0.0
            if leave_hours <= 0:
                continue

            lt = self._get_annual_leave_type()
            if not lt:
                raise UserError(_("Annual Leave type not found."))

            leave_days = leave_hours / 8.0

            leave = self.env["hr.leave"].create({
                "name": _("Auto Lateness Deduction (%s)") % (slip.name or ""),
                "employee_id": slip.employee_id.id,
                "holiday_status_id": lt.id,
                "request_date_from": slip.date_to,
                "request_date_to": slip.date_to,
                "number_of_days": leave_days,
            })

            leave.action_validate()
            slip.late_leave_id = leave.id

        return res
