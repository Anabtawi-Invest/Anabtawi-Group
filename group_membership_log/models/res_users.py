# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        before_map = {}
        if 'group_ids' in vals:
            tracked_exists = self.env['res.groups'].search_count([
                ('membership_log_enabled', '=', True),
            ])
            if tracked_exists:
                before_map = {user.id: set(user.group_ids.ids) for user in self}

        res = super().write(vals)

        if before_map:
            after_map = {user.id: set(user.group_ids.ids) for user in self}
            self.env['group.membership.log']._log_membership_diff(before_map, after_map)

        return res
