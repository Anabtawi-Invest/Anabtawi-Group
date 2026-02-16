# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_pce_reconcile(self):
        for run in self:
            slips = run.slip_ids
            if not slips:
                raise UserError(_("No payslips in this payrun."))
            slips.action_pce_reconcile()
        return True
