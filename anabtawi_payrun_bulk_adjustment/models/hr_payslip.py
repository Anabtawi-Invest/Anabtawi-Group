from odoo import models, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_export_template(self):
        """Directly exports the Excel template for selected payslips or payrun."""
        payrun = self.mapped('payslip_run_id')
        payrun_id = payrun[0].id if payrun else self._context.get('active_id')
        
        wizard = self.env['hr.payslip.run.import.wizard'].create({
            'payrun_id': payrun_id if payrun_id else False,
        })
        return wizard.with_context(active_ids=self.ids, active_model='hr.payslip').action_export_template()

    def action_open_bulk_adjustment_wizard(self):
        """Opens the Upload Bulk Adjustment wizard."""
        payrun = self.mapped('payslip_run_id')
        payrun_id = payrun[0].id if payrun else self._context.get('active_id')

        return {
            'name': _("Upload Bulk Salary Adjustments"),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payrun_id': payrun_id,
                'active_ids': self.ids or self._context.get('active_ids', []),
            },
        }
