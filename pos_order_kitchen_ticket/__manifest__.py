# -*- coding: utf-8 -*-
{
    "name": "POS Order Ticket After Receipt",
    "version": "19.0.1.0.8",
    "category": "Point of Sale",
    "summary": "Print a second ticket (order number and products, no prices) after the customer receipt",
    "description": """
POS Order Ticket After Receipt
==============================

When enabled on a POS configuration, a second ticket is printed right after
the first customer receipt of a paid order, on the same printer and as a
separate print job (so the printer cuts between the two tickets).

The ticket shows the order number and the products with their quantities,
without any prices, so the customer can hand it to the employee preparing
the order. Reprints and refund orders do not print this ticket.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_config_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_order_kitchen_ticket/static/src/app/receipt_header.xml",
            "pos_order_kitchen_ticket/static/src/app/order_kitchen_ticket.js",
            "pos_order_kitchen_ticket/static/src/app/order_kitchen_ticket.xml",
            "pos_order_kitchen_ticket/static/src/app/pos_store_patch.js",
            "pos_order_kitchen_ticket/static/src/app/receipt_screen_patch.js",
            "pos_order_kitchen_ticket/static/src/app/receipt_screen.xml",
            "pos_order_kitchen_ticket/static/src/app/order_receipt_patch.js",
            "pos_order_kitchen_ticket/static/src/app/order_receipt.xml",
            "pos_order_kitchen_ticket/static/src/app/order_kitchen_ticket.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
