from odoo import models, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_open_bulk_adjustment_wizard(self):
        """Opens the Bulk Salary Adjustments import/export wizard for selected payslips or payrun."""
        payrun = self.mapped('payslip_run_id')
        payrun_id = payrun[0].id if payrun else self._context.get('active_id')
        if not payrun_id and self._context.get('default_payslip_run_id'):
            payrun_id = self._context.get('default_payslip_run_id')

        return {
            'name': _("Bulk Salary Adjustments"),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payrun_id': payrun_id,
                'active_ids': self.ids or self._context.get('active_ids', []),
            },
        }
