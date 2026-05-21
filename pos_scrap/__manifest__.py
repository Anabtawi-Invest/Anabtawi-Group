# -*- coding: utf-8 -*-
{
    "name": "POS Scrap",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Create stock scrap directly from POS",
    "author":"Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "stock"],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_scrap/static/src/app/screens/product_screen/control_buttons_scrap.xml",
            "pos_scrap/static/src/app/screens/product_screen/control_buttons_scrap.js",
            "pos_scrap/static/src/app/screens/product_screen/scrap_popup/scrap_popup.js",
            "pos_scrap/static/src/app/screens/product_screen/scrap_popup/scrap_popup.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

