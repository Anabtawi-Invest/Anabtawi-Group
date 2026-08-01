# -*- coding: utf-8 -*-
{
    'name': 'Acting Employee Login',
    'summary': 'Identify the acting employee at login and show them in chatter',
    'description': """
Require an employee number and employee password at login (in addition to the
normal user credentials). The employee must be linked to the signing-in user.
The acting employee name is stored on mail messages and shown beside the
username in chatter for models belonging to modules selected in Settings.
    """,
    'category': 'Hidden',
    'author': 'enbtawi',
    'version': '19.0.1.2.4',
    'depends': [
        'base_setup',
        'hr',
        'hr_employee_code',
        'mail',
        'stock',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
        'views/acting_branch_access_views.xml',
        'views/stock_picking_views.xml',
        'views/login_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'acting_employee_login/static/src/core/common/**/*',
        ],
        'mail.assets_public': [
            'acting_employee_login/static/src/core/common/**/*',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
