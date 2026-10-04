# -*- coding: utf-8 -*-
{
    "name": "POS Order Ticket After Receipt",
    "version": "19.0.1.0.0",
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
        "receipt/pos_order_kitchen_ticket.xml",
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_order_kitchen_ticket/static/src/app/pos_ticket_printer_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
