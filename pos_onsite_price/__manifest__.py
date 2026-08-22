# -*- coding: utf-8 -*-
{
    "name": "POS On-Site Prices",
    "author": "Anabtawi",
    "version": "19.0.1.0.15",
    "category": "Point of Sale",
    "summary": "Quantity-range kilo pricing for on-site and off-site POS orders",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "pos_advance_order",
        "pos_pledge_order",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_onsite_price_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_onsite_price/static/src/js/onsite_price_popup.js",
            "pos_onsite_price/static/src/xml/onsite_price_popup.xml",
            "pos_onsite_price/static/src/js/onsite_price_utils.js",
            "pos_onsite_price/static/src/js/onsite_price_order.js",
            "pos_onsite_price/static/src/js/onsite_price_pay.js",
            "pos_onsite_price/static/src/js/onsite_price_advance.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
