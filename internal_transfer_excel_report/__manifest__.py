{
    'name': 'Internal Transfer Excel Report-Anabtawi',
    'version': '1.5.1',
    'author': 'Anabtawi',
    'license': 'LGPL-3',
    'depends': ['stock', 'factory_plan_category'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'views/wizard_view.xml',
    ],
    'installable': True,
}
