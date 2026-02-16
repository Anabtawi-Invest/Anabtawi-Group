# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_mass_reconciliation(self):
        for run in self:
            if not run.slip_ids:
                raise UserError(_("No payslips found in this batch."))
            run.slip_ids.action_reconcile_lateness()
        return True
