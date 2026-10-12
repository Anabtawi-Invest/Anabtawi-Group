# -*- coding: utf-8 -*-
{
    "name": "POS Local SQL Backup - Custom Cakes",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Copy special cake orders to the cashier PC backup",
    "description": """
POS Local SQL Backup - Custom Cakes
===================================

Custom cake orders are created on the server from the cake form, so the
regular local backup never sees "pay later" cakes. This bridge sends every cake
order created, saved for later payment or loaded for payment from the POS to
the "Anabtawi POS Local Backup" helper, and links the POS order that pays for
the cake. Failed attempts are recorded too.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["pos_local_sql_backup", "pos_custom_cake"],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_local_sql_backup_cake/static/src/app/cake_backup.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
