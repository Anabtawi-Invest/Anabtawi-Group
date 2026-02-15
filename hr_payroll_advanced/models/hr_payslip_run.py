# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def _ensure_all_slips_reconciled(self):
        for run in self:
            pending = run.slip_ids.filtered(lambda s: s.reconciliation_state != "reconciled")
            if pending:
                names = ", ".join(pending.mapped("employee_id.name"))
                raise UserError(
                    "Cannot validate/close this Pay Run because reconciliation is still Pending for: %s\n"
                    "Please reconcile the payslips first." % (names,)
                )

    # Different databases use different method names; override safely.
    def close_payslip_run(self):
        self._ensure_all_slips_reconciled()
        return super().close_payslip_run()

    def action_close(self):
        self._ensure_all_slips_reconciled()
        return super().action_close()

    def action_validate(self):
        self._ensure_all_slips_reconciled()
        return super().action_validate()
