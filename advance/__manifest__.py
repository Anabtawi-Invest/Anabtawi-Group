# -*- coding: utf-8 -*-
{
    "name": "POS Advance Order (Arboon) - Odoo 19",
    "version": "19.0.2.0.0",
    "category": "Point of Sale",
    "summary": "Create advance (deposit) orders in POS without invoice or stock move, and print receipt with products + advance.",
    "depends": ["point_of_sale", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/pos_advance_payment_views.xml",
        "views/pos_config_views.xml",

    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_button.js",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_button.xml",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_details_popup.js",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_details_popup.xml",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/payment_screen.js",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/pay_advance.xml",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_order_list_popup.js",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_order_list_popup.xml",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/complete_advance_order_button.js",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_report.xml",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/advance_receipt.js",
            "advance/static/src/app/screens/product_screen/control_buttons/advance_button/order_receipt.xml",

        ],
    },
    "installable": True,
    "application": False,
}
