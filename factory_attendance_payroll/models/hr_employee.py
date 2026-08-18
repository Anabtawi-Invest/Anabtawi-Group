from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    lunch_break_rule = fields.Selection([
        ('factory_branch', 'Factory & Branches (1.0 Hour Break)'),
        ('head_office', 'Head Office (0.5 Hour Break)')
    ], string="Lunch Break Rule", default='factory_branch', help="Defines the break duration deducted from daily attendance.")

    def _get_lunch_break_duration(self):
        self.ensure_one()
        try:
            if hasattr(self, 'lunch_break_rule') and self.lunch_break_rule == 'head_office':
                return 0.5
            elif self.department_id and ('head office' in self.department_id.name.lower() or 'hq' in self.department_id.name.lower()):
                return 0.5
            elif self.resource_calendar_id and 'head office' in self.resource_calendar_id.name.lower():
                return 0.5
        except Exception:
            pass
        return 1.0
