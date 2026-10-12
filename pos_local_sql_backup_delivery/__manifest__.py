# -*- coding: utf-8 -*-
{
    "name": "POS Local SQL Backup - Cash Delivery",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Copy cash deliveries to the cashier PC backup",
    "description": """
POS Local SQL Backup - Cash Delivery
====================================

Sends every cash delivery made from the POS (during the session and while
closing it) to the "Anabtawi POS Local Backup" helper, with the available cash
shown to the cashier at that moment. Refused deliveries are recorded too.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["pos_local_sql_backup", "pos_delivery_amount"],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_local_sql_backup_delivery/static/src/app/delivery_backup.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
