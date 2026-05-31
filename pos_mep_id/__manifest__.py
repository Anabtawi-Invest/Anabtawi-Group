# -*- coding: utf-8 -*-
{
    "name": "POS MEP ID",
    "version": "19.0.1.0.0",
    "summary": "Capture MEP ID for selected POS payment methods",
    "category": "Point of Sale",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_mep_id/static/src/pos/mep_id_popup.js",
            "pos_mep_id/static/src/pos/payment_mep_id_patch.js",
            "pos_mep_id/static/src/pos/mep_id_popup.xml",
        ],
    },
    "installable": True,
    "application": False,
}
