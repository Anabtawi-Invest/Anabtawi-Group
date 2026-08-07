{
    'name': 'Daily Pos Sales Report',
    'version': '10.12',
    'author': 'Ameen Arabiyat - Rana Faris',
    'category': 'Point of Sale',
    'summary': 'Daily operations summary report by POS branch',
    'depends': [
        'point_of_sale',
        'pos_exclusive_payment_method',
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
