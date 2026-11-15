# -*- coding: utf-8 -*-
{
    "name": "POS Local SQL Backup - Advance Orders",
    "version": "19.0.1.4.2",
    "category": "Point of Sale",
    "summary": "Copy advance orders and pledge returns to the cashier PC backup",
    "description": """
POS Local SQL Backup - Advance Orders
=====================================

Advance orders and pledge returns are handled directly on the server, so the
regular local backup (which watches the orders kept in the browser) never sees
them. This bridge sends every advance action made from the POS (deposit,
completion, refund), every Return Pledge, and the POS orders the server
creates for them, to the "Anabtawi POS Local Backup" helper.

The copy is taken from the form before Odoo is called, so a create, completion,
or refund is stored on the cashier PC even when the shop cannot reach Odoo.
When Odoo answers, the same local row receives the official advance number.

When the POS session opens, the advance form lists and the completable
advance-paid orders are saved in the browser. Offline create keeps a local
advance. Offline complete can finish that local advance or an AO that was
already online when the list was last saved. When the connection returns,
create is synced first (by local_uuid), then completion.

Events wait in the browser storage while the helper is not reachable and are
sent as soon as it is back.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["pos_local_sql_backup", "pos_advance_order", "pos_pledge_order"],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_local_sql_backup_advance/static/src/app/complete_advance_cache.js",
            "pos_local_sql_backup_advance/static/src/app/local_advance_store.js",
            "pos_local_sql_backup_advance/static/src/app/advance_backup.js",
            "pos_local_sql_backup_advance/static/src/app/advance_popup_cache.js",
            "pos_local_sql_backup_advance/static/src/app/complete_advance_offline.js",
            "pos_local_sql_backup_advance/static/src/app/pledge_return_backup.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
