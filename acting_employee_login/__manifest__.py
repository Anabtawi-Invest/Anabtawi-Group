# -*- coding: utf-8 -*-
{
    'name': 'Acting Employee Login',
    'summary': 'Identify the acting employee or branch at login and show them in chatter',
    'description': """
Require a second name and password at login (in addition to the normal user
credentials).

Normal users validate against the employee Acting Login Password.
Branch users validate against branch access records configured under
Inventory > Configuration > Branch Login Access.

The acting identity is stored on mail messages and shown beside the username
in chatter for modules selected in Settings.
    """,
    'category': 'Hidden',
    'author': 'enbtawi',
    'version': '1.6.1',
    'depends': [
        'base_setup',
        'hr',
        'mail',
        'web',
        'stock',
    ],
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/ir.model.access.csv',
        'views/acting_branch_access_views.xml',
        'views/hr_employee_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'views/login_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'acting_employee_login/static/src/core/common/**/*',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
