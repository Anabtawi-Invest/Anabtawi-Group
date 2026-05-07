# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Mobile Single Device',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Bind one mobile app device per user (portal or internal) with Bearer tokens',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/mobile_device_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
