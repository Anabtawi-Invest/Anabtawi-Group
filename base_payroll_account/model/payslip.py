# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_existing_lines(self, line_ids, line, account_id, debit, credit):
        """This will help to Separate the Journal Entry lines for each partner"""
        line_partner_id = False
        existing_lines = (
            line_id for line_id in line_ids if
            line_id['name'] == line.name
            and line_id.get('partner_id') == line_partner_id
            and line_id['account_id'] == account_id
            and ((line_id['debit'] > 0 and credit <= 0) or (line_id['credit'] > 0 and debit <= 0))
            and (
                    (
                        not line_id['analytic_distribution'] and
                        not line.salary_rule_id.analytic_account_id.id and
                        not line.slip_id.contract_id.analytic_account_id.id
                    )
                    or line_id['analytic_distribution'] and line.salary_rule_id.analytic_account_id.id in line_id['analytic_distribution']
                    or line_id['analytic_distribution'] and line.slip_id.contract_id.analytic_account_id.id in line_id['analytic_distribution']

                )
        )
        return existing_lines
