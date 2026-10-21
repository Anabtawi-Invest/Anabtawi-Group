# -*- coding: utf-8 -*-
{
    'name': 'Factory to Branch Transfer Excel Report',
    'version': '19.0.1.0.0',
    'summary': 'Export done factory→branch stock transfers to Excel (date filtered)',
    'category': 'Accounting/Accounting',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': ['stock', 'account'],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'data': [
        'security/ir.model.access.csv',
        'wizard/factory_branch_transfer_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
