from odoo import api, models

OFFICER_XMLID = 'hr_payroll.group_hr_payroll_user'
MANAGER_XMLID = 'hr_payroll.group_hr_payroll_manager'
READONLY_XMLID = 'payroll_readonly.group_hr_payroll_readonly'
PAYROLL_FIELD_GROUPS = frozenset({OFFICER_XMLID, MANAGER_XMLID})


def _group_xmlids(groups):
    if not isinstance(groups, str):
        return frozenset()
    return frozenset(part.strip().lstrip('!') for part in groups.split(',') if part.strip())


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _has_field_access(self, field, operation):
        if super()._has_field_access(field, operation):
            return True
        # Payroll locks salary fields to Officer / Administrator. Read Only may
        # see those fields. Write stays with the original groups, so a user who
        # can edit the employee contract still cannot change wage or contract dates.
        if operation != 'read':
            return False
        if not PAYROLL_FIELD_GROUPS.intersection(_group_xmlids(field.groups)):
            return False
        return self.env.user.has_groups(READONLY_XMLID)
