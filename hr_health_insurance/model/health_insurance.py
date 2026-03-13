# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from datetime import date
import logging
_logger = logging.getLogger(__name__)

class HealthInsurance(models.Model):
    _name = "health.insurance"
    _description = "Health Insurance"

    name = fields.Char("Name")
    birthdate = fields.Date("Birthdate")
    currency_id = fields.Many2one("res.currency", related="employee_id.company_id.currency_id", store=True)
    age = fields.Integer("Age", compute="_compute_age")
    employee_id = fields.Many2one("hr.employee", string="Employee")
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')], string="Gender")
    relationship = fields.Selection([("employee", "Employee"),
                                     ("spouse", "Spouse"),
                                     ("child", "Child"),
                                     ("parent", "Parent")], required=True, string="Relationship")
    notes = fields.Text("Notes")
    marital_status_info = fields.Selection([("single", "Single"),
                                            ("married", "Married"),
                                            ("divorced", "Divorced"),
                                            ("widower", "Widower")], default="single", string="Status")
    grade_id = fields.Many2one('hr.health.grade', string='Grade', required=True)
    effective_date = fields.Date("Effective Date", required=True)
    policy_full_amount = fields.Float('Policy Full Amount', compute="_compute_policy_full_amount")
    employee_contribution = fields.Float('Employee Contribution (%)', default=0.0)
    manual_contribution = fields.Float('Manual Contribution', default=0.0)
    monthly_contribution = fields.Float('Monthly Contribution', compute="_compute_monthly_contribution", default=0.0)

    @api.depends('age', 'grade_id', 'effective_date')
    def _compute_policy_full_amount(self):

        for rec in self:
            contract_id = self.env['hr.health.contract'].search(
                [('start_date', '<=', rec.effective_date), ('contract_grade_id', '=', rec.grade_id.id),
                 ('end_date', '>=', rec.effective_date)], limit=1)
            if contract_id:
                age_group = contract_id.age_group_ids.filtered(lambda group: group.from_age <= rec.age <= group.to_age)
                rec.policy_full_amount = age_group[0].amount if age_group else 0.0
            else:
                rec.policy_full_amount = 0.0

    @api.depends('policy_full_amount', 'employee_contribution')
    def _compute_monthly_contribution(self):
        for rec in self:
            if rec.effective_date :
                rec.monthly_contribution = rec.policy_full_amount * (rec.employee_contribution / 100) / 12
            else:
                rec.monthly_contribution = 0

    @api.onchange('relationship')
    def _onchange_relationship(self):
        if self.relationship == "employee":
            self.name = self.employee_id.name
            self.birthdate = self.employee_id.birthday
            # Odoo 19 uses `sex` on hr.employee/hr.version instead of `gender`.
            self.gender = self.employee_id.sex
        else:
            self.name = False
            self.birthdate = False
            self.gender = False

    @api.depends('birthdate')
    def _compute_age(self):
        today = date.today()
        for rec in self:
            if rec.birthdate:
                rec.age = today.year - rec.birthdate.year
            else:
                rec.age = 0

    @api.onchange('relationship')
    def _onchange_relationship(self):
        if self.relationship == "employee":
            self.name = self.employee_id.name
            self.birthdate = self.employee_id.birthday
            self.gender = self.employee_id.sex
            self.employee_contribution = 69.35  # ← هون أضفنا القيمة
        else:
            self.name = False
            self.birthdate = False
            self.gender = False
            self.employee_contribution = 100

    @api.onchange('employee_id', 'relationship')
    def _onchange_employee_data(self):
        import logging
        _logger = logging.getLogger(__name__)

        for rec in self:
            _logger.warning("Onchange triggered")
            _logger.warning("Employee: %s", rec.employee_id)
            _logger.warning("Relationship: %s", rec.relationship)

            if rec.employee_id and rec.relationship == "employee":

                rec.name = rec.employee_id.name
                rec.birthdate = rec.employee_id.birthday
                rec.gender = rec.employee_id.sex
                rec.marital_status_info = rec.employee_id.marital
                rec.employee_contribution = 69.35

                grade = self.env['hr.health.grade'].search([], order='id', limit=1)

                _logger.warning("Found grade: %s", grade)

                if grade:
                    rec.grade_id = grade
                    _logger.warning("Assigned grade_id: %s", rec.grade_id)