{
    'name': 'POS Cash Movement Excel Report',
    'version': '1.0',
    'author': 'Anabtawi',
    'category': 'Point of Sale',
    'summary': 'Excel report for cash delivery and cash-out movements per transaction',
    'depends': [
        'point_of_sale',
        'pos_delivery_amount',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/pos_cash_movement_wizard_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
