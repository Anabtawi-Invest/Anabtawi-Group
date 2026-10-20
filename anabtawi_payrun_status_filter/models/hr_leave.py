# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _get_employee_domain(self):
        """Exclude terminated employees from selection when creating or requesting Time Off."""
        domain = super()._get_employee_domain()
        return Domain.AND([domain, [('profile_employment_status', '!=', 'terminated')]])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            emp_id = vals.get('employee_id')
            if emp_id:
                emp = self.env['hr.employee'].browse(emp_id)
                if emp.profile_employment_status == 'terminated':
                    raise ValidationError(
                        _("Cannot create a time off request for terminated employee '%s'.") % emp.name
                    )
        return super().create(vals_list)

    def write(self, vals):
        if 'employee_id' in vals and vals['employee_id']:
            emp = self.env['hr.employee'].browse(vals['employee_id'])
            if emp.profile_employment_status == 'terminated':
                raise ValidationError(
                    _("Cannot assign a time off request to terminated employee '%s'.") % emp.name
                )
        return super().write(vals)
