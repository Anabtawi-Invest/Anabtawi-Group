# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    tax_id = fields.Char(
        string='الرقم الضريبي للموظف',
        help='Employee Tax Identification Number (الرقم الضريبي الشخصي لدى دائرة الضريبة)',
        tracking=True
    )
    national_id = fields.Char(
        string='الرقم الوطني / جواز السفر',
        help='National ID or Passport Number'
    )
    name_arabic = fields.Char(
        string='الاسم بالعربي',
        help='Employee Full Name in Arabic'
    )

    def action_open_income_tax_wizard(self):
        """Opens the Income Tax Report (AR/3) wizard for the current employee."""
        self.ensure_one()
        return {
            'name': 'شهادة ضريبة الدخل والرواتب (AR/3)',
            'type': 'ir.actions.act_window',
            'res_model': 'income.tax.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_id': self.id,
                'default_tax_year': '2025',
            }
        }
