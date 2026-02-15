from odoo import models


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_bulk_reconcile_lateness_engine(self):
        for run in self:
            # reconcile each slip (FULL AUTO v2)
            for slip in run.slip_ids:
                slip.action_reconcile_lateness_engine_v2()
        return True
