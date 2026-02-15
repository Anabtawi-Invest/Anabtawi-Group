# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HrEmployeeOTBank(models.Model):
    _name = "hr.employee.ot.bank"
    _description = "Employee OT Bank Ledger"
    _order = "date desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="cascade")
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    slip_id = fields.Many2one("hr.payslip", ondelete="set null", index=True)
    reference = fields.Char()
    delta_hours = fields.Float(required=True, help="Positive adds hours, negative consumes hours.")
    balance_after = fields.Float(readonly=True)

    def name_get(self):
        res = []
        for r in self:
            res.append((r.id, f"{r.employee_id.name}: {r.delta_hours:+.2f}h on {r.date}"))
        return res

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    ot_bank_balance_hours = fields.Float(
        string="OT Bank Balance (Hours)",
        compute="_compute_ot_bank_balance_hours",
    )

    def _compute_ot_bank_balance_hours(self):
        # Read-only compute (no writes) to stay registry-safe
        Ledger = self.env["hr.employee.ot.bank"].sudo()
        for emp in self:
            last = Ledger.search([("employee_id", "=", emp.id)], order="date desc, id desc", limit=1)
            emp.ot_bank_balance_hours = last.balance_after if last else 0.0

    def _pce_post_ot_bank_delta(self, delta_hours, date, slip=None, reference=None):
        self.ensure_one()
        Ledger = self.env["hr.employee.ot.bank"].sudo()
        last = Ledger.search([("employee_id", "=", self.id)], order="date desc, id desc", limit=1)
        prev = last.balance_after if last else 0.0
        new_bal = prev + (delta_hours or 0.0)
        rec = Ledger.create({
            "employee_id": self.id,
            "date": date,
            "slip_id": slip.id if slip else False,
            "reference": reference or (slip.name if slip else ""),
            "delta_hours": delta_hours or 0.0,
            "balance_after": new_bal,
        })
        return rec
