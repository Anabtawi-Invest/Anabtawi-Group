{
    'name': 'Internal Transfer Excel Report-Anabtawi',
    'version': '1.2',
    "author":"Anabtawi",
    'depends': ['stock', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/wizard_view.xml',
        'views/delivery_transaction_report_wizard_views.xml',
        'report/delivery_transaction_report_templates.xml',
        'report/delivery_transaction_report_action.xml',
    ],
    'installable': True,
}
