# -*- coding: utf-8 -*-
{
    "name": "POS MEPS Terminal Integration",
    "version": "19.0.4.0.0",
    "summary": "MEPS/ApexECR POS card payments (Sale/Void/Settlement over SOAP), fully customer-configurable",
    "category": "Point of Sale",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "external_dependencies": {"python": ["lxml", "requests", "openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "views/pos_payment_method_views.xml",
        "views/pos_order_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/meps_terminal_import_wizard_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_mep_id/static/src/pos/meps_waiting_popup.js",
            "pos_mep_id/static/src/pos/payment_meps_patch.js",
            "pos_mep_id/static/src/pos/meps_waiting_popup.xml",
        ],
    },
    "installable": True,
    "application": False,
}
