# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    employee_id = fields.Many2one(
        'hr.employee',
        domain="[('profile_employment_status', '!=', 'terminated')]",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            emp_id = vals.get('employee_id')
            if emp_id:
                emp = self.env['hr.employee'].browse(emp_id)
                if emp.profile_employment_status == 'terminated':
                    raise ValidationError(
                        _("Cannot record attendance for terminated employee '%s'.") % emp.name
                    )
        return super().create(vals_list)

    def write(self, vals):
        if 'employee_id' in vals and vals['employee_id']:
            emp = self.env['hr.employee'].browse(vals['employee_id'])
            if emp.profile_employment_status == 'terminated':
                raise ValidationError(
                    _("Cannot assign attendance to terminated employee '%s'.") % emp.name
                )
        return super().write(vals)
