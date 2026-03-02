from odoo import models

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_export_xlsx_en(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/invoice_xlsx_export/{self.id}?lang=en_US",
            "target": "self",
        }

    def action_export_xlsx_ar(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/invoice_xlsx_export/{self.id}?lang=ar_001",
            "target": "self",
        }
