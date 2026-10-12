# -*- coding: utf-8 -*-
{
    "name": "POS Local SQL Backup - Advance Orders",
    "version": "19.0.1.1.0",
    "category": "Point of Sale",
    "summary": "Copy advance orders and pledge returns to the cashier PC backup",
    "description": """
POS Local SQL Backup - Advance Orders
=====================================

Advance orders and pledge returns are handled directly on the server, so the
regular local backup (which watches the orders kept in the browser) never sees
them. This bridge sends every advance action made from the POS (deposit,
completion, refund), every Return Pledge, and the POS orders the server
creates for them, to the "Anabtawi POS Local Backup" helper. Failed attempts
are recorded too.

Events wait in the browser storage while the helper is not reachable and are
sent as soon as it is back.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["pos_local_sql_backup", "pos_advance_order", "pos_pledge_order"],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_local_sql_backup_advance/static/src/app/advance_backup.js",
            "pos_local_sql_backup_advance/static/src/app/pledge_return_backup.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
