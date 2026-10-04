# -*- coding: utf-8 -*-
{
    "name": "POS Local SQL Backup",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Copy every POS order to an encrypted SQLite database on the cashier PC",
    "description": """
POS Local SQL Backup
====================

Sends every POS order (open, paid, cancelled, deleted) to the
"Anabtawi POS Local Backup" helper running on the cashier PC, which stores
them in an encrypted local SQLite database. The browser storage and the
normal synchronization with Odoo are not changed; sending to the helper never
blocks a sale.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_local_sql_backup/static/src/app/pos_store_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
