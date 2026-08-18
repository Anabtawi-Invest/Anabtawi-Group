from odoo import models, fields, api

class IrModelData(models.Model):
    _inherit = 'ir.model.data'

    def _register_hook(self):
        """
        Runs when models are loaded into registry during module upgrade.
        Neutralizes all legacy XML tracking records for factory_attendance_payroll by setting noupdate=True,
        permanently preventing Odoo module upgrader from attempting to delete orphan records on staging databases.
        """
        res = super()._register_hook()
        try:
            legacy_data = self.sudo().search([
                ('module', '=', 'factory_attendance_payroll'),
                ('noupdate', '=', False)
            ])
            if legacy_data:
                legacy_data.write({'noupdate': True})
        except Exception:
            pass
        return res

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    lunch_break_rule = fields.Selection([
        ('factory', 'Factory / Branches (1.0h Break)'),
        ('office', 'Head Office (0.5h Break)'),
        ('custom', 'Custom Break Duration')
    ], string="Lunch Break Deduction Policy", compute="_compute_lunch_break_rule", store=False)

    custom_lunch_break_hours = fields.Float(
        string="Custom Lunch Break (Hours)",
        default=1.0,
        help="Custom lunch break duration in hours if 'Custom Break Duration' is selected."
    )

    @api.depends('department_id')
    def _compute_lunch_break_rule(self):
        for emp in self:
            dept_name = (emp.department_id.name or '').lower() if emp.department_id else ''
            if 'head' in dept_name or 'office' in dept_name or 'hq' in dept_name or 'administration' in dept_name:
                emp.lunch_break_rule = 'office'
            else:
                emp.lunch_break_rule = 'factory'

    def _get_lunch_break_duration(self):
        """
        Returns the lunch break duration in hours for this employee based on location/department:
        - Factory / Branches: 1.0 hour (60 mins)
        - Head Office: 0.5 hour (30 mins)
        - Custom: custom_lunch_break_hours
        """
        self.ensure_one()
        if self.lunch_break_rule == 'office':
            return 0.5
        elif self.lunch_break_rule == 'custom':
            return max(0.0, self.custom_lunch_break_hours)
        else:
            return 1.0
