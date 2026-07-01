# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Enable membership tracking on all existing groups after install."""
    env['res.groups'].with_context(skip_group_membership_log=True).search([]).write({
        'membership_log_enabled': True,
    })
