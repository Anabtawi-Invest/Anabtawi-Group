# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class HP(models.Model):
    _inherit = "hr.payslip"

    def _prepare_line_values(self, line, account_id, date, debit, credit):
        vals = super(HP, self)._prepare_line_values(line, account_id, date, debit, credit)
        ref = self.company_id.hi_reference_employee_in_journal_entries
        account = self.company_id.hi_account_id.id
        if ref and vals["account_id"] == account:
            vals["partner_id"] = (self.employee_id.user_id and self.employee_id.user_id.partner_id.id) or \
                                 self.employee_id.work_contact_id.id
        return vals
