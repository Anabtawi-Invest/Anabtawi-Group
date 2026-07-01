# -*- coding: utf-8 -*-

from odoo import fields, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    membership_log_enabled = fields.Boolean(
        string='Track Membership Changes',
        default=True,
        help='When enabled, adding or removing users from this group is logged.',
    )

    def write(self, vals):
        before_map = {}
        if 'user_ids' in vals:
            groups_to_track = self.filtered('membership_log_enabled')
            if groups_to_track:
                before_map = {group.id: set(group.user_ids.ids) for group in groups_to_track}

        res = super().write(vals)

        if before_map:
            after_map = {
                group.id: set(group.user_ids.ids)
                for group in self.browse(before_map.keys())
            }
            self.env['group.membership.log']._log_group_users_diff(before_map, after_map)

        return res
