# -*- coding: utf-8 -*-
{
    'name': 'Acting Employee Login',
    'summary': 'Identify the acting employee at login and show them in chatter',
    'description': """
Require an employee name and employee password at login (in addition to the
normal user credentials). The acting employee name is stored on mail messages
and shown beside the username in chatter for models belonging to modules
selected in Settings.
    """,
    'category': 'Hidden',
    'author': 'enbtawi',
    'version': '1.5',
    'depends': [
        'base_setup',
        'hr',
        'mail',
        'web',
    ],
    'data': [
        'views/hr_employee_views.xml',
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
