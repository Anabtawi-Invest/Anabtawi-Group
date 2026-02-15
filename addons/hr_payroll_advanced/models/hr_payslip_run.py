from odoo import models, fields


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_bulk_reconcile_lateness_engine(self):
        """
        FULL ENGINE:
        - recompute slips
        - run reconcile logic
        - update columns + status
        """
        for run in self:
            # Ensure slips exist
            slips = run.slip_ids
            if not slips:
                continue

            # Bulk reconcile each slip
            slips.action_reconcile_lateness_engine()

        return True
