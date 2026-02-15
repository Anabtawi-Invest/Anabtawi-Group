# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    overtime_bank_balance = fields.Monetary(
        string="OT Bank Balance",
        compute="_compute_ot_bank_balance",
        currency_field="company_id.currency_id",
        store=False,
    )

    @api.depends("address_home_id", "company_id")
    def _compute_ot_bank_balance(self):
        AccountMoveLine = self.env["account.move.line"]
        for emp in self:
            total = 0.0
            partner = emp.address_home_id
            if not partner:
                emp.overtime_bank_balance = 0.0
                continue

            # We compute from the Overtime Payable account lines linked to the employee partner.
            # Using internal_group = 'liability' is safe. If you want to target a specific account,
            # filter by account_id.id instead.
            lines = AccountMoveLine.search([
                ("partner_id", "=", partner.id),
                ("account_id.internal_group", "=", "liability"),
                ("name", "ilike", "OT_TOTAL"),
            ])
            for l in lines:
                total += (l.credit - l.debit)

            emp.overtime_bank_balance = total
