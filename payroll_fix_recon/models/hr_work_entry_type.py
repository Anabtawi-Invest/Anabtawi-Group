# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    pfr_pay_percent = fields.Float(
        string="Payroll Pay %", default=100.0,
        help="Share of the daily wage paid for each day of this type on the payslip "
             "(100 = full day, 7.5 = 7.5% of the daily wage, 0 = unpaid).")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('round_days', 'NO') != 'NO' and not vals.get('round_days_type'):
                vals['round_days_type'] = 'DOWN'
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('round_days') in ('HALF', 'FULL') and not vals.get('round_days_type'):
            vals['round_days_type'] = 'DOWN'
        return super().write(vals)

    def _pfr_pay_factor(self):
        self.ensure_one()
        return (self.pfr_pay_percent if self.pfr_pay_percent is not None else 100.0) / 100.0
