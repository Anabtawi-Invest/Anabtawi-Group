from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    lunch_break_rule = fields.Selection([
        ('factory_branch', 'Factory & Branches (1.0 Hour Break)'),
        ('head_office', 'Head Office (0.5 Hour Break)')
    ], string="Lunch Break Rule", compute="_compute_lunch_break_rule", inverse="_inverse_lunch_break_rule", store=False, help="Defines the break duration deducted from daily attendance.")

    def _compute_lunch_break_rule(self):
        for emp in self:
            try:
                dept_name = (emp.department_id.name or '').lower() if emp.department_id else ''
                cal_name = (emp.resource_calendar_id.name or '').lower() if emp.resource_calendar_id else ''
                if 'head office' in dept_name or 'hq' in dept_name or 'head office' in cal_name:
                    emp.lunch_break_rule = 'head_office'
                else:
                    emp.lunch_break_rule = 'factory_branch'
            except Exception:
                emp.lunch_break_rule = 'factory_branch'

    def _inverse_lunch_break_rule(self):
        pass

    def _get_lunch_break_duration(self):
        self.ensure_one()
        if self.lunch_break_rule == 'head_office':
            return 0.5
        return 1.0
