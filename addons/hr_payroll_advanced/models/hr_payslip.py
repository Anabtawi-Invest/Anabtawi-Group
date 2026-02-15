from odoo import models, fields, api


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # =====================================================
    # RECONCILE STATUS BADGE
    # =====================================================

    reconciliation_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("reconciled", "Reconciled"),
        ],
        default="pending",
        string="Reconcile Status",
        tracking=True,
    )

    # =====================================================
    # LIVE ENGINE — AUTO RESET STATUS
    # =====================================================

    def _reset_reconcile_if_changed(self):
        for slip in self:
            if slip.reconciliation_state == "reconciled":
                slip.reconciliation_state = "pending"

    # =====================================================
    # TRIGGER WHEN WORK ENTRIES CHANGE
    # =====================================================

    @api.depends("worked_days_line_ids.number_of_hours")
    def _compute_worked_days_line_ids(self):
        super()._compute_worked_days_line_ids()
        self._reset_reconcile_if_changed()

    # =====================================================
    # TRIGGER WHEN INPUTS CHANGE
    # =====================================================

    @api.depends("input_line_ids.amount")
    def _compute_input_line_ids(self):
        super()._compute_input_line_ids()
        self._reset_reconcile_if_changed()

    # =====================================================
    # TRIGGER WHEN COMPUTE SHEET RUNS
    # =====================================================

    def compute_sheet(self):
        res = super().compute_sheet()
        self._reset_reconcile_if_changed()
        return res

    # =====================================================
    # FULL RECONCILIATION ENGINE (FINAL v2)
    # =====================================================

    def action_reconcile_lateness_engine_v2(self):
        for slip in self:

            lateness_hours = slip.late_hours or 0.0
            ot_available = slip.ot_total_amount or 0.0
            leave_available = slip.leave_hours_available or 0.0

            ot_deduct = 0.0
            leave_deduct = 0.0
            salary_deduct = 0.0

            # 1️⃣ Deduct from OT Bank
            if lateness_hours > 0 and ot_available > 0:
                ot_deduct = min(lateness_hours, ot_available)
                lateness_hours -= ot_deduct

            # 2️⃣ Deduct from Annual Leave
            if lateness_hours > 0 and leave_available > 0:
                leave_deduct = min(lateness_hours, leave_available)
                lateness_hours -= leave_deduct

            # 3️⃣ Remaining goes to salary deduction
            if lateness_hours > 0:
                salary_deduct = lateness_hours

            slip.write({
                "ot_deduct_hours": ot_deduct,
                "leave_deduct_hours": leave_deduct,
                "salary_deduct_hours": salary_deduct,
                "reconciliation_state": "reconciled",
            })
