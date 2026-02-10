from odoo import models


class HrPayslip(models.Model):
_inherit = 'hr.payslip'


def _cron_auto_compute_sheet(self):
slips = self.search([('state', '=', 'draft')])
for slip in slips:
slip.compute_sheet()
