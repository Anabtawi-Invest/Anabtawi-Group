# -*- coding: utf-8 -*-

from odoo import api, fields, models


class GroupMembershipLog(models.Model):
    _name = 'group.membership.log'
    _description = 'Group Membership Change Log'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        ondelete='cascade',
        index=True,
    )
    group_id = fields.Many2one(
        'res.groups',
        string='Group',
        required=True,
        ondelete='cascade',
        index=True,
    )
    action = fields.Selection(
        selection=[
            ('add', 'Added'),
            ('remove', 'Removed'),
        ],
        string='Action',
        required=True,
        index=True,
    )
    performed_by_id = fields.Many2one(
        'res.users',
        string='Performed By',
        required=True,
        ondelete='restrict',
        index=True,
    )
    date = fields.Datetime(
        string='Date',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    display_name = fields.Char(compute='_compute_display_name')

    @api.depends('user_id', 'group_id', 'action', 'date')
    def _compute_display_name(self):
        for log in self:
            user_name = log.user_id.display_name or '?'
            group_name = log.group_id.full_name or log.group_id.name or '?'
            action_label = dict(self._fields['action'].selection).get(log.action, log.action)
            log.display_name = f'{user_name} — {action_label} — {group_name}'

    @api.model
    def _should_log(self):
        if self.env.context.get('install_mode') or self.env.context.get('module'):
            return False
        if self.env.context.get('skip_group_membership_log'):
            return False
        return True

    @api.model
    def _log_membership_diff(self, before_map, after_map):
        """Compare {record_id: set(group_ids)} maps and log differences."""
        if not self._should_log():
            return

        tracked_groups = self.env['res.groups'].search([
            ('membership_log_enabled', '=', True),
        ])
        if not tracked_groups:
            return

        tracked_ids = set(tracked_groups.ids)
        performed_by = self.env.user
        now = fields.Datetime.now()
        vals_list = []

        for record_id, before_ids in before_map.items():
            after_ids = after_map.get(record_id, set())
            for group_id in after_ids - before_ids:
                if group_id in tracked_ids:
                    vals_list.append({
                        'user_id': record_id,
                        'group_id': group_id,
                        'action': 'add',
                        'performed_by_id': performed_by.id,
                        'date': now,
                    })
            for group_id in before_ids - after_ids:
                if group_id in tracked_ids:
                    vals_list.append({
                        'user_id': record_id,
                        'group_id': group_id,
                        'action': 'remove',
                        'performed_by_id': performed_by.id,
                        'date': now,
                    })

        if vals_list:
            self.sudo().create(vals_list)

    @api.model
    def _log_group_users_diff(self, before_map, after_map):
        """Compare {group_id: set(user_ids)} when editing from the group form."""
        if not self._should_log():
            return

        performed_by = self.env.user
        now = fields.Datetime.now()
        vals_list = []

        for group_id, before_ids in before_map.items():
            group = self.env['res.groups'].browse(group_id)
            if not group.membership_log_enabled:
                continue
            after_ids = after_map.get(group_id, set())
            for user_id in after_ids - before_ids:
                vals_list.append({
                    'user_id': user_id,
                    'group_id': group_id,
                    'action': 'add',
                    'performed_by_id': performed_by.id,
                    'date': now,
                })
            for user_id in before_ids - after_ids:
                vals_list.append({
                    'user_id': user_id,
                    'group_id': group_id,
                    'action': 'remove',
                    'performed_by_id': performed_by.id,
                    'date': now,
                })

        if vals_list:
            self.sudo().create(vals_list)
