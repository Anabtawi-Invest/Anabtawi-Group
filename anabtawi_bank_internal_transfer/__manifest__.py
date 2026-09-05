# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Bank Internal Transfer',
    'version': '19.0.1.0.2',
    'category': 'Contacts',
    'summary': 'Map banks to internal transfer values on partner bank accounts',
    'depends': ['contacts', 'hr'],
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/bank_internal_transfer_mapping_views.xml',
        'views/res_partner_bank_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
