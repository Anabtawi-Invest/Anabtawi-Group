{
    'name': 'Internal Transfer Excel Report-Anabtawi',
    'version': '1.6.0',
    'author': 'Anabtawi',
    'license': 'LGPL-3',
    'depends': ['stock', 'purchase_stock', 'factory_plan_category'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'views/wizard_view.xml',
    ],
    'installable': True,
}
