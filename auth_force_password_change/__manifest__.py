# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Force Password Change on First Login',
    'version': '19.0.1.0.5',
    'category': 'Hidden/Tools',
    'summary': 'Require users to set a new password on first login',
    'depends': ['auth_signup', 'remember_device_login'],
    'data': [
        'views/res_users_views.xml',
        'views/login_templates.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
}
