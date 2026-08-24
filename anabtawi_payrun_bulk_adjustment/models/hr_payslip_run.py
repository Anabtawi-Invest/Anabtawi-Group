from odoo import models, _


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_open_bulk_adjustment_wizard(self):
        """Opens the Bulk Salary Adjustments import/export wizard for this payrun."""
        self.ensure_one()
        return {
            'name': _("Bulk Salary Adjustments"),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payrun_id': self.id,
            },
        }
