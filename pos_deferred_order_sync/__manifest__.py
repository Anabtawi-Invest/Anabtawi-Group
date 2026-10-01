# -*- coding: utf-8 -*-
{
    "name": "POS Deferred Order Sync",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Keep paid POS orders on the device and send them to the server when the register closes",
    "description": """
POS Deferred Order Sync
=======================

When enabled on a POS configuration, paid orders are stored locally on the
device (like offline mode) even while the connection is online, and are sent
to the server when the register is closed. All other server calls keep
working online.

Orders that need the server immediately are still sent right away:
refunds (with their original order), invoiced orders, custom cake orders,
pledge / employee service orders, scheduled (fulfillment) orders and orders
that already exist on the server.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_deferred_order_sync/static/src/app/pos_store_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
