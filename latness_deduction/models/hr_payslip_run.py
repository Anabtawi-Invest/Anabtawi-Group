from odoo import models, _

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def _action_mass_reconcile_lateness_no_ot_bank(self):
        for run in self:
            run.slip_ids.action_reconcile_lateness_no_ot_bank()
        return {'type': 'ir.actions.client', 'tag': 'reload'}