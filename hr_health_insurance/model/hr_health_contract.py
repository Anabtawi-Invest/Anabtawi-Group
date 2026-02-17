# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class HRHealthAgeGroup(models.Model):
    _name = "hr.health.age.group"
    _description = "HR Health Age Group"

    health_contract_id = fields.Many2one('hr.health.contract', string='Contract', required=True)
    from_age = fields.Integer(string="Age From", required=True)
    to_age = fields.Integer(string="Age To", required=True)
    amount = fields.Float(string="Amount", required=True)

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.from_age} - {record.to_age}"
            result.append((record.id, name))
        return result

    @api.constrains('from_age', 'to_age', 'health_contract_id')
    def _check_age_overlap(self):
        for record in self:
            if record.from_age >= record.to_age:
                raise ValidationError("The 'Age From' must be less than 'Age To'.")

            overlapping_periods = self.search([
                ('id', '!=', record.id),
                ('health_contract_id', '=', record.health_contract_id.id),
                '&',
                ('from_age', '<=', record.from_age),
                ('to_age', '>=', record.from_age)
            ])

            if overlapping_periods:
                raise ValidationError(
                    "The age range overlaps with an existing range for the same contract."
                )

class HRHealthContract(models.Model):
    _name = "hr.health.contract"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "HR Health Contract"

    name = fields.Char(string='Name', required=True, tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, string='Company')
    contract_grade_id = fields.Many2one('hr.health.grade', string='Contract Grade', required=True, tracking=True)
    start_date = fields.Date('Start Date', required=True, tracking=True)
    end_date = fields.Date('End Date', required=True, tracking=True)
    age_group_ids = fields.One2many('hr.health.age.group', 'health_contract_id', string='Age Groups')

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for record in self:
            if record.start_date and record.end_date and record.start_date > record.end_date:
                raise ValidationError(_("The start date must be before the end date."))

    @api.constrains('start_date', 'end_date', 'company_id')
    def _check_no_overlapping_contracts(self):
        for record in self:
            overlapping_contracts = self.env['hr.health.contract'].search([
                ('id', '!=', record.id), ('company_id', '=', record.company_id.id),
                ('contract_grade_id', '=', record.contract_grade_id.id),
                '|', '&',
                ('end_date', '>=', record.start_date),
                ('start_date', '<=', record.start_date),
                '&',
                ('end_date', '>=', record.end_date),
                ('start_date', '<=', record.end_date),
            ])

            if overlapping_contracts:
                raise ValidationError(_(
                    "The contract from %(start_date)s to %(end_date)s overlaps with an existing contract.",
                    start_date=record.start_date,
                    end_date=record.end_date
                ))
