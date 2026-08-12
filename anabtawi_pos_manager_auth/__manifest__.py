# -*- coding: utf-8 -*-
{
    "name": "Anabtawi POS Manager Security Authorization",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Require Manager Barcode or PIN scan for POS Refunds, Order Cancellations, Price/Discount Overrides, and Cash Moves",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "pos_hr",
    ],
    "data": [
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "anabtawi_pos_manager_auth/static/src/app/pos_store_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
