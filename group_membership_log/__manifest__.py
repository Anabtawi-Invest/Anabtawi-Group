# -*- coding: utf-8 -*-
{
    'name': 'Group Membership Log',
    'version': '19.0.1.0.1',
    'summary': 'Log when users are added to or removed from selected groups',
    'author': 'Anabtawi',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/group_membership_log_views.xml',
        'views/res_groups_views.xml',
    ],
    'installable': True,
    'application': False,
    'post_init_hook': 'post_init_hook',
}
