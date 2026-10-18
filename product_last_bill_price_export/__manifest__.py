# -*- coding: utf-8 -*-
{
    'name': 'Product Last Bill Price Export',
    'version': '19.0.1.0.3',
    'summary': 'Export all products with their last vendor bill (purchase) price to Excel',
    'category': 'Purchases',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': ['purchase', 'account'],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'data': [
        'security/ir.model.access.csv',
        'wizard/product_last_bill_price_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
