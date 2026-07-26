{
    'name': 'POS Daily Operations Report',
    'version': '4.0',
    'author': 'Anabtawi',
    'category': 'Point of Sale',
    'summary': 'Daily operations summary report by POS branch',
    'depends': [
        'point_of_sale',
        'pos_advance_order',
        'pos_delivery_amount',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_payment_method_views.xml',
        'wizard/pos_daily_operations_wizard_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
