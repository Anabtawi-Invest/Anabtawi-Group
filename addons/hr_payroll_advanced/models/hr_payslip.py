from odoo import models, fields


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # =====================================================
    # RECONCILIATION STATUS BADGE
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
    # SAFE RESET ENGINE
    # =====================================================

    def _reset_reconcile_if_changed(self):
        for slip in self:
            if slip.reconciliation_state == "reconciled":
                slip.reconciliation_state = "pending"

    # =====================================================
    # SAFE HOOK — DO NOT OVERRIDE COMPUTE METHODS
    # =====================================================

    def write(self, vals):
        res = super().write(vals)

        trigger_fields = {
            "worked_days_line_ids",
            "input_line_ids",
            "line_ids",
        }

        if trigger_fields.intersection(vals.keys()):
            self._reset_reconcile_if_changed()

        return res

    # =====================================================
    # ALSO RESET WHEN PAYSLIP RECOMPUTES
    # =====================================================

    def compute_sheet(self):
        res = super().compute_sheet()
        self._reset_reconcile_if_changed()
        return res

    # =====================================================
    # FINAL RECONCILIATION ENGINE
    # =====================================================

    def action_reconcile_lateness_engine_v2(self):
        for slip in self:

            lateness_hours = slip.late_hours or 0.0
            ot_available = slip.ot_total_amount or 0.0
            leave_available = slip.leave_hours_available or 0.0

            ot_deduct = 0.0
            leave_deduct = 0.0
            salary_deduct = 0.0

            # Deduct OT
            if lateness_hours > 0 and ot_available > 0:
                ot_deduct = min(lateness_hours, ot_available)
                lateness_hours -= ot_deduct

            # Deduct Annual Leave
            if lateness_hours > 0 and leave_available > 0:
                leave_deduct = min(lateness_hours, leave_available)
                lateness_hours -= leave_deduct

            # Remaining = salary
            if lateness_hours > 0:
                salary_deduct = lateness_hours

            slip.write({
                "ot_deduct_hours": ot_deduct,
                "leave_deduct_hours": leave_deduct,
                "salary_deduct_hours": salary_deduct,
                "reconciliation_state": "reconciled",
            })
