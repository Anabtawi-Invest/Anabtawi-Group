from odoo import models

class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_open_lateness_preview(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "lateness.preview.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payrun_id": self.id},
        }