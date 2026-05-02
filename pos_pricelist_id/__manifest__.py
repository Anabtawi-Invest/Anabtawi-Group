# -*- coding: utf-8 -*-
{
    'name': 'POS Pricelist  id enhancement-anabtawi  ',
    'version': '1.2',
    'category': 'Point of Sale',
    'summary': 'Manage pledge (Rahn) scenarios with employees, delivery, and accounting',
    'description': """
   
    """,
    'author': 'Enbtawi Sweet',
    'depends': ['point_of_sale', 'pos_sale', 'account', 'hr'],
    'data': [
        "views/product_pricelist.xml",

    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_pricelist_id/static/src/pos/id_number_validation.js",
            "pos_pricelist_id/static/src/pos/receipt_header.xml",
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
