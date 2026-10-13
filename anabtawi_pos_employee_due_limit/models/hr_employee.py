# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.tools import float_compare


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _get_employee_due_wage(self):
        self.ensure_one()
        return self.sudo().current_version_id.wage or 0.0

    def _get_employee_due_limit(self):
        """Limit in the employee's company currency: (wage - wage * deduction%) * max%."""
        self.ensure_one()
        company = self.company_id or self.env.company
        wage = self._get_employee_due_wage()
        net_wage = wage - wage * company.employee_due_deduction_percent / 100.0
        limit = net_wage * company.employee_due_max_percent / 100.0
        return company.currency_id.round(max(limit, 0.0))

    def _sync_employee_due_credit_limit(self):
        employees = self.sudo().filtered(
            lambda e: e.work_contact_id and e.company_id.employee_due_limit_enabled
        )
        if not employees:
            return
        companies = self.env["res.company"].sudo().search([])
        for employee in employees:
            limit = employee._get_employee_due_limit()
            rounding = employee.company_id.currency_id.rounding
            for company in companies:
                partner = employee.work_contact_id.with_company(company)
                if float_compare(partner.credit_limit, limit, precision_rounding=rounding):
                    partner.credit_limit = limit
        employees.work_contact_id._refresh_pos_customer_account_due()

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._sync_employee_due_credit_limit()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if {"work_contact_id", "company_id", "active"} & set(vals):
            self._sync_employee_due_credit_limit()
        return res

    @api.model
    def _cron_sync_employee_due_credit_limit(self):
        self.sudo().search([])._sync_employee_due_credit_limit()
