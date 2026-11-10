import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

READONLY_MODULE = 'payroll_readonly'
READONLY_NAME = 'group_hr_payroll_readonly'
READONLY_XMLID = f'{READONLY_MODULE}.{READONLY_NAME}'
GROUP_LABEL = 'Read Only'
GROUP_COMMENT = (
    'Open payroll and view payslips, pay runs, and salary setup. '
    'Cannot create, edit, or delete payroll documents.'
)


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _setup_payroll_readonly(self):
        """Create the Payroll / Read Only role and copy Officer visibility.

        Reuses a Read Only group already created by hand on the Payroll
        privilege, so installing this module does not add a second role.
        """
        officer = self.env.ref('hr_payroll.group_hr_payroll_user')
        manager = self.env.ref('hr_payroll.group_hr_payroll_manager', raise_if_not_found=False)
        readonly = self._payroll_readonly_group(officer)

        blocked = officer
        if manager:
            blocked |= manager
        if readonly.implied_ids & blocked:
            readonly.implied_ids = [(3, group.id) for group in (readonly.implied_ids & blocked)]

        self._payroll_readonly_access(officer, readonly)
        self._payroll_readonly_rules(officer, readonly)
        self._payroll_readonly_menus(officer, readonly)
        self.env.registry.clear_cache()
        _logger.info('Payroll Read Only group is ready (id=%s).', readonly.id)
        return True

    @api.model
    def _payroll_readonly_group(self, officer):
        privilege = officer.privilege_id
        group = self.env.ref(READONLY_XMLID, raise_if_not_found=False)
        if not group and privilege:
            group = self.search([
                ('name', '=', GROUP_LABEL),
                ('privilege_id', '=', privilege.id),
            ], limit=1)
        if not group:
            group = self.create({
                'name': GROUP_LABEL,
                'privilege_id': privilege.id,
                'sequence': (officer.sequence or 10) - 5,
                'comment': GROUP_COMMENT,
                'share': False,
            })
        else:
            group.write({
                'name': GROUP_LABEL,
                'privilege_id': privilege.id,
                'sequence': (officer.sequence or 10) - 5,
                'comment': GROUP_COMMENT,
            })
        self._payroll_readonly_xmlid(group)
        return group

    @api.model
    def _payroll_readonly_xmlid(self, group):
        data = self.env['ir.model.data'].sudo().search([
            ('module', '=', READONLY_MODULE),
            ('name', '=', READONLY_NAME),
            ('model', '=', 'res.groups'),
        ], limit=1)
        if data:
            if data.res_id != group.id:
                data.write({'res_id': group.id, 'noupdate': True})
            return data
        return self.env['ir.model.data'].sudo().create({
            'module': READONLY_MODULE,
            'name': READONLY_NAME,
            'model': 'res.groups',
            'res_id': group.id,
            'noupdate': True,
        })

    @api.model
    def _payroll_readonly_access(self, officer, readonly):
        Access = self.env['ir.model.access'].sudo()
        read_values = {
            'perm_read': True,
            'perm_write': False,
            'perm_create': False,
            'perm_unlink': False,
        }
        officer_models = officer.model_access.filtered(
            lambda access: access.perm_read and not access.model_id.transient
        ).model_id
        existing = Access.search([('group_id', '=', readonly.id)])
        covered = self.env['ir.model']
        for access in existing:
            model = access.model_id
            if model.transient:
                access.unlink()
                continue
            if model not in officer_models:
                continue
            if model in covered:
                access.unlink()
                continue
            if any(access[key] != value for key, value in read_values.items()):
                access.write(read_values)
            covered |= model
        for model in officer_models - covered:
            Access.create({
                'name': f'{model.model} payroll read only',
                'model_id': model.id,
                'group_id': readonly.id,
                **read_values,
            })

    @api.model
    def _payroll_readonly_rules(self, officer, readonly):
        rules = officer.rule_groups
        if not rules:
            return
        groups_field = 'groups' if 'groups' in rules._fields else 'group_ids'
        if groups_field not in rules._fields:
            return
        for rule in rules:
            if readonly not in rule[groups_field]:
                rule.write({groups_field: [(4, readonly.id)]})

    @api.model
    def _payroll_readonly_menus(self, officer, readonly):
        menus = self.env['ir.ui.menu']
        for menu in officer.menu_access:
            action = menu.action
            if action and action._name == 'ir.actions.server':
                continue
            if self._payroll_action_is_transient(action):
                continue
            menus |= menu
            self._payroll_readonly_action_group(action, officer, readonly)
        if menus:
            readonly.menu_access = [(4, menu.id) for menu in menus]
        if officer.view_access:
            readonly.view_access = [(4, view.id) for view in officer.view_access]

    @api.model
    def _payroll_action_is_transient(self, action):
        if not action or action._name != 'ir.actions.act_window' or not action.res_model:
            return False
        model = self.env.get(action.res_model)
        return bool(model is not None and model._transient)

    @api.model
    def _payroll_readonly_action_group(self, action, officer, readonly):
        if not action or 'groups_id' not in action._fields:
            return
        if officer in action.groups_id and readonly not in action.groups_id:
            action.groups_id = [(4, readonly.id)]
