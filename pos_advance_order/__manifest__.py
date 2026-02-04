# -*- coding: utf-8 -*-
{
    "name": "POS Advance Order",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Create and manage advance orders for POS pickup",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "product",
        "account",
        "hr",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/pos_advance_order_views.xml",
        "views/pos_config_views.xml",
        "views/res_partner_views.xml",
        "views/product_pledge_views.xml",
        "report/pos_advance_order_report.xml",
        "report/pos_advance_order_receipt.xml",
        "report/pos_advance_order_full_receipt.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}

