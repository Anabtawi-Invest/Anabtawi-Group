# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Bank Internal Transfer Code',
    'version': '19.0.1.0.0',
    'category': 'Contacts',
    'summary': 'Internal transfer code on banks, related on bank accounts',
    'depends': ['base'],
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'data': [
        'views/res_bank_views.xml',
        'views/res_partner_bank_views.xml',
    ],
    'installable': True,
    'application': False,
    'post_init_hook': 'post_init_hook',
}
