from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # =====================================================
    # LIVE OT BANK (Amount)
    # =====================================================

    overtime_bank_balance = fields.Monetary(
        string="OT Bank Balance",
        compute="_compute_ot_bank_balance",
        currency_field="company_id.currency_id",
        store=False,
    )

    # =====================================================
    # COMPUTE OT BANK FROM ACCOUNTING LIABILITY
    # =====================================================

    def _compute_ot_bank_balance(self):
        AccountMoveLine = self.env["account.move.line"]

        for emp in self:

            total = 0.0

            # Sum liability lines linked to employee partner
            lines = AccountMoveLine.search([
                ("partner_id", "=", emp.address_home_id.id),
                ("account_id.internal_group", "=", "liability"),
                ("name", "ilike", "OT_TOTAL"),
            ])

            for l in lines:
                total += (l.credit - l.debit)

            emp.overtime_bank_balance = total
