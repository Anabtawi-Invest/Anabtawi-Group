# -*- coding: utf-8 -*-
{
    "name": "POS Hospitality Gift",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Gift lines with 100% discount and hospitality expense posting",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account"],
    "data": [
        "views/pos_config_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_hospitality_gift/static/src/app/screens/product_screen/control_buttons_gift.xml",
            "pos_hospitality_gift/static/src/app/screens/product_screen/control_buttons_gift.js",
            "pos_hospitality_gift/static/src/app/models/pos_order_line_gift.js",
            "pos_hospitality_gift/static/src/app/components/orderline/orderline_gift.xml",
            "pos_hospitality_gift/static/src/app/components/orderline/orderline_gift.css",
            "pos_hospitality_gift/static/src/app/screens/receipt_screen/receipt/order_receipt_gift.js",
            "pos_hospitality_gift/static/src/app/screens/receipt_screen/receipt/order_receipt_gift.xml",
        ],
    },
    "installable": True,
    "application": False,
}
