# -*- coding: utf-8 -*-
{
    "name": "       POS Advance Order-two cashiers ",
    "author":"Anabtawi",
    "version": "19.0.2.0.7",
    "category": "Point of Sale",
    "summary": "Create and manage advance orders for POS pickup",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "product",
        "account",
        "hr",
        "employee_request",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/pos_advance_order_views.xml",
        "views/pos_advance_order_employee_pricelist_wizard_views.xml",
        "views/pos_config_views.xml",
        "views/res_partner_views.xml",
        "views/pos_order.xml",
        "views/pos_pledge_views.xml",
        "views/product_pledge_views.xml",
        "views/pos_advance_discount_views.xml",

        "report/pos_advance_order_report.xml",
        "report/pos_advance_order_receipt.xml",
        "report/pos_advance_order_full_receipt.xml",

    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_advance_order/static/src/app/screens/product_screen/payment_button_visibility.xml",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/advance_order_receipt.js",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/advance_order_receipt.xml",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup.js",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup.xml",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/complete_advance_order_popup.js",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/complete_advance_order_popup.xml",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/advance_order_button.js",
            "pos_advance_order/static/src/app/screens/product_screen/control_buttons/advance_order_button/advance_order_button.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

