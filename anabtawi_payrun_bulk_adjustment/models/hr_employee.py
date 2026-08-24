from odoo import models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def action_open_bulk_adjustment_wizard(self):
        """Opens the Upload Bulk Adjustment wizard from the Employees module."""
        return {
            'name': _("Upload Bulk Salary Adjustments"),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_ids': self.ids or self._context.get('active_ids', []),
            },
        }
