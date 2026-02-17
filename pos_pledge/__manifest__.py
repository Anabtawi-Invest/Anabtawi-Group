# -*- coding: utf-8 -*-
{
    'name': 'POS Pledge (Rahn) Management',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Manage pledge (Rahn) scenarios with employees, delivery, and accounting',
    'description': """
        POS Pledge (Rahn) Management
        =============================
        
        Features:
        ---------
        * Pledge product tracking
        * Employee service handling
        * Delivery service management
        * Dual receipt generation (internal + customer)
        * Automatic accounting entries
        * Pledge return with reversal entries
        * Three business case scenarios supported
    """,
    'author': 'Your Company',
    'depends': ['point_of_sale', 'pos_sale', 'account', 'hr', 'pos_advance_order'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/product_data.xml',
        'views/product_template_views.xml',
        'views/pos_order_views.xml',
        'views/pos_pledge_views.xml',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_pledge/static/src/js/pledge_list_popup.js',
            'pos_pledge/static/src/js/employee_selection_popup.js',
            'pos_pledge/static/src/js/pos_pledge.js',
            'pos_pledge/static/src/xml/pledge_list_popup.xml',
            'pos_pledge/static/src/xml/employee_selection_popup.xml',
            'pos_pledge/static/src/xml/control_buttons.xml',
            'pos_pledge/static/src/xml/receipt_screen.xml',
            'pos_pledge/static/src/xml/receipts.xml',
            'pos_pledge/static/src/css/pledge_receipts.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
