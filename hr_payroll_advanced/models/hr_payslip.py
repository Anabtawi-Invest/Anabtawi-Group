from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # ======================================
    # RECONCILIATION STATUS (LIVE ENGINE)
    # ======================================

    reconciliation_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("reconciled", "Reconciled"),
        ],
        string="Reconcile Status",
        default="pending",
        tracking=True,
    )

    # ======================================
    # METRICS FIELDS (SAFE FLOAT ONLY)
    # ======================================

    late_hours = fields.Float(string="Late Hours")
    ot_total_amount = fields.Float(string="Overtime Total")
    leave_hours_available = fields.Float(string="Annual Leave")
    ot_deduct_hours = fields.Float(string="OT Deduct")
    leave_deduct_hours = fields.Float(string="Leave Deduct")
    salary_deduct_hours = fields.Float(string="Salary Deduct")

    # ======================================
    # HR RECONCILE BUTTON
    # ======================================

    def action_reconcile_lateness_engine(self):
        for slip in self:

            late = slip.late_hours or 0.0
            ot = slip.ot_total_amount or 0.0
            leave = slip.leave_hours_available or 0.0

            ot_used = min(late, ot)
            late -= ot_used

            leave_used = min(late, leave)
            late -= leave_used

            slip.ot_deduct_hours = ot_used
            slip.leave_deduct_hours = leave_used
            slip.salary_deduct_hours = late

            slip.reconciliation_state = "reconciled"

        return True

    # ======================================
    # AUTO RESET WHEN CHANGES
    # ======================================

    def write(self, vals):
        res = super().write(vals)

        if any(k in vals for k in ["worked_days_line_ids", "input_line_ids", "line_ids"]):
            for rec in self:
                rec.reconciliation_state = "pending"

        return res

    # ======================================
    # PAYROLL CONTROL ENGINE
    # ======================================

    def action_payslip_done(self):
        for slip in self:
            if slip.reconciliation_state != "reconciled":
                raise UserError(_("Please Reconcile Lateness before validating Payslip."))

        return super().action_payslip_done()
