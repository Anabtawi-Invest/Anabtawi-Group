# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def _ensure_all_reconciled(self):
        for run in self:
            pending = run.slip_ids.filtered(lambda s: s.reconciliation_state != "reconciled")
            if pending:
                names = ", ".join(pending.mapped("employee_id.name"))
                raise UserError(
                    _("Cannot close/validate Pay Run because reconciliation is Pending for: %s\n"
                      "Reconcile the payslips first.") % names
                )

    def close_payslip_run(self):
        self._ensure_all_reconciled()
        return super().close_payslip_run()

    def action_close(self):
        self._ensure_all_reconciled()
        return super().action_close()

    def action_validate(self):
        self._ensure_all_reconciled()
        return super().action_validate()
