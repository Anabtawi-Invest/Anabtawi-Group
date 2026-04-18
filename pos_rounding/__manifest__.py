# -*- coding: utf-8 -*-
{
    'name': 'POS Rounding-anabtawi',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Track paid but uncollected POS orders',
    'description': """
POS Collect Later
=================

This module allows POS orders to be marked as "Collect Later" when customers 
pay in full but don't collect their orders immediately.

Features:
---------
* Add "Collect Later" checkbox in POS
* Mandatory popup for collection details (expected date, notes)
* Track paid but uncollected orders
* Employee view to manage pending collections
* Mark orders as collected when customer returns
* Full accounting compliance (invoices remain paid)
    """,
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'account', 'sale', 'pos_sale'],
    'data': [
        "views/pos_config_views.xml",
        "views/report_invoice.xml",
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_rounding/static/src/app/models/pos_order.js',
            'pos_rounding/static/src/app/screens/product_screen/control_buttons_rounding.xml',
            'pos_rounding/static/src/app/screens/product_screen/control_buttons_rounding.js',
        ],
        'web.assets_backend': [
            'pos_rounding/static/src/components/tax_totals/tax_totals.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
