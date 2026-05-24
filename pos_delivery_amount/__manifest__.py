# pos_delivery_amount/__manifest__.py

{
    'name': 'Delivery Amount',
    'version': '19.0.1.0.0',
    'summary': 'POS Delivery Amount Enhancement - Bank Deposit Tracking at Session Close',
    'description': """
        Enhances the Point of Sale session closing workflow to allow the cashier
        to enter the amount that will be deposited to the bank on the next business day.
        Creates the related accounting entry automatically and maintains full compliance
        with standard Odoo accounting and access rights behavior.
    """,
    'author': 'Custom Development',
    'category': 'Point of Sale',
    'depends': [
        'point_of_sale',
        'account',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_config_views.xml',
        'views/pos_session_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_delivery_amount/static/src/js/DeliveryAmountPopup.js',
            'pos_delivery_amount/static/src/js/ClosePosPopupExtension.js',
            'pos_delivery_amount/static/src/xml/DeliveryAmountPopup.xml',
            'pos_delivery_amount/static/src/css/delivery_amount.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
