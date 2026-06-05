# -*- coding: utf-8 -*-
{
    'name': 'POS Self Order Location',
    'version': '1.0.2',
    'category': 'Point of Sale',
    'summary': 'Require customer location on mobile self-orders and track them in a dedicated model',
    'depends': ['pos_self_order', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/pos_self_order_request_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'pos_self_order.assets': [
            'pos_self_order_location/static/src/self_order/**/*.xml',
            'pos_self_order_location/static/src/self_order/**/*.js',
        ],
        'point_of_sale.assets_prod': [
            'pos_self_order_location/static/src/pos/**/*.xml',
            'pos_self_order_location/static/src/pos/**/*.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
