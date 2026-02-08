# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayrunReconciliation(models.Model):
    """Audit log of a single reconciliation execution per employee per pay run.

    Stores hours ONLY. Monetary impact is handled by salary rules reading inputs.
    """

    _name = "hr.payrun.reconciliation"
    _description = "Pay Run Reconciliation (Hours)"
    _order = "execution_datetime desc, id desc"
    _rec_name = "employee_id"

    pay_run_id = fields.Many2one(
        "hr.payslip.run",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="pay_run_id.company_id",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True)

    # Hours (audit)
    lateness_hours = fields.Float(string="Lateness Hours", digits="Payroll", readonly=True)
    ot_used_hours = fields.Float(string="OT Used Hours", digits="Payroll", readonly=True)
    annual_used_hours = fields.Float(string="Annual Leave Used Hours", digits="Payroll", readonly=True)
    late_unpaid_hours = fields.Float(string="Unpaid Lateness Hours", digits="Payroll", readonly=True)

    # Traceability
    execution_datetime = fields.Datetime(readonly=True)
    executed_by = fields.Many2one("res.users", readonly=True)

    # Links to generated records (for rollback)
    payslip_id = fields.Many2one("hr.payslip", readonly=True, ondelete="set null")
    ot_input_id = fields.Many2one("hr.payslip.input", readonly=True, ondelete="set null")
    annual_input_id = fields.Many2one("hr.payslip.input", readonly=True, ondelete="set null")
    late_unpaid_input_id = fields.Many2one("hr.payslip.input", readonly=True, ondelete="set null")
    annual_leave_id = fields.Many2one("hr.leave", readonly=True, ondelete="set null")

    state = fields.Selection(
        [("draft", "Draft"), ("applied", "Applied")],
        default="draft",
        required=True,
        readonly=True,
        index=True,
    )

    _sql_constraints = [
        (
            "uniq_payrun_employee",
            "unique(pay_run_id, employee_id)",
            "A reconciliation record already exists for this employee in this pay run.",
        )
    ]

    def action_open_related(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": "Reconciliation",
            "res_model": "hr.payrun.reconciliation",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
        return action
