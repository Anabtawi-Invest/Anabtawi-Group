from odoo import models, fields
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    reconciliation_state = fields.Selection(
        [("pending", "Pending"), ("reconciled", "Reconciled")],
        default="pending",
        string="Reconcile Status",
        tracking=True,
    )

    def _reset_reconcile_if_changed(self):
        for slip in self:
            if slip.reconciliation_state == "reconciled":
                slip.reconciliation_state = "pending"

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {"worked_days_line_ids", "input_line_ids", "line_ids"}
        if trigger_fields.intersection(vals.keys()):
            self._reset_reconcile_if_changed()
        return res

    def compute_sheet(self):
        res = super().compute_sheet()
        self._reset_reconcile_if_changed()
        return res

    # -----------------------------------------------------
    # PAYROLL CONTROL ENGINE: BLOCK VALIDATION IF PENDING
    # -----------------------------------------------------
    def _ensure_reconciled_before_validate(self):
        pending = self.filtered(lambda s: s.reconciliation_state != "reconciled")
        if pending:
            names = ", ".join(pending.mapped("employee_id.name"))
            raise UserError(
                "Cannot validate payslip(s) because reconciliation is still Pending for: %s\n"
                "Please press Reconcile first." % (names,)
            )

    # Odoo commonly validates payslips via this method
    def action_payslip_done(self):
        self._ensure_reconciled_before_validate()
        return super().action_payslip_done()

    # Some flows use this button name
    def action_validate(self):
        self._ensure_reconciled_before_validate()
        return super().action_validate()

    # Some databases use this method name
    def action_validate_sheet(self):
        self._ensure_reconciled_before_validate()
        return super().action_validate_sheet()

    # Your reconcile engine (keep yours if already there)
    def action_reconcile_lateness_engine_v2(self):
        for slip in self:
            lateness_hours = slip.late_hours or 0.0
            ot_available = slip.ot_total_amount or 0.0
            leave_available = slip.leave_hours_available or 0.0

            ot_deduct = 0.0
            leave_deduct = 0.0
            salary_deduct = 0.0

            if lateness_hours > 0 and ot_available > 0:
                ot_deduct = min(lateness_hours, ot_available)
                lateness_hours -= ot_deduct

            if lateness_hours > 0 and leave_available > 0:
                leave_deduct = min(lateness_hours, leave_available)
                lateness_hours -= leave_deduct

            if lateness_hours > 0:
                salary_deduct = lateness_hours

            slip.write({
                "ot_deduct_hours": ot_deduct,
                "leave_deduct_hours": leave_deduct,
                "salary_deduct_hours": salary_deduct,
                "reconciliation_state": "reconciled",
            })
