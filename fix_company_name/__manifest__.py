# -*- coding: utf-8 -*-
{
    'name': 'Fix Company Name DB Column',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Emergency fix to convert res_company.name and res_partner.name from jsonb back to varchar',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': ['base'],
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
}
