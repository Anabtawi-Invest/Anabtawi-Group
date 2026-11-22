# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_overtime_calculation = fields.Boolean(
        string="Enable Overtime Calculation", default=True,
        help="When unchecked, extra hours do not generate overtime on payslips.")
    fap_annual_leave_type_id = fields.Many2one(
        'hr.leave.type', string="Reconciliation Annual Leave Type",
        domain="[('time_type', '=', 'leave'), ('company_id', 'in', [False, id])]",
        help="Annual leave type used for lateness deduction and termination settlement. "
             "Falls back to a name search ('Annual Leave') when empty.")
    pfr_advance_journal_id = fields.Many2one(
        'account.journal', string="Mid-Month Advance Journal",
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash', 'general'))]",
        help="Default journal used when posting mid-month salary advances.")
    pfr_advance_debit_account_id = fields.Many2one(
        'account.account', string="Mid-Month Advance Debit Account",
        check_company=True,
        help="Employee Advance / Receivable account debited at mid-month and cleared by the month-end payslip.")
    pfr_advance_credit_account_id = fields.Many2one(
        'account.account', string="Mid-Month Advance Credit Account",
        check_company=True,
        help="Bank / Cash / Clearing account credited when paying mid-month salary advances.")


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_overtime_calculation = fields.Boolean(
        related='company_id.enable_overtime_calculation', readonly=False)
    fap_annual_leave_type_id = fields.Many2one(
        related='company_id.fap_annual_leave_type_id', readonly=False)
    pfr_advance_journal_id = fields.Many2one(
        related='company_id.pfr_advance_journal_id', readonly=False)
    pfr_advance_debit_account_id = fields.Many2one(
        related='company_id.pfr_advance_debit_account_id', readonly=False)
    pfr_advance_credit_account_id = fields.Many2one(
        related='company_id.pfr_advance_credit_account_id', readonly=False)
