# -*- coding: utf-8 -*-
{
    "name": "POS Local SQL Backup - Custom Cakes",
    "version": "19.0.1.0.1",
    "category": "Point of Sale",
    "summary": "Copy custom cake orders to the cashier PC backup and sync offline creates",
    "description": """
POS Local SQL Backup - Custom Cakes
===================================

Custom cake create / pay-later / load are handled by server RPCs, so the regular
local order backup never sees them. This bridge sends every cake action made
from the POS to the "Anabtawi POS Local Backup" helper.

When the POS session opens online, cake configuration and waiting pay-later
orders are cached. Offline create (pay now or pay later) keeps a local cake
(with local_uuid). When the connection returns, cakes sync to Odoo first
(idempotent by local_uuid, MO created on the server), then the POS order
cake link is updated before the sale syncs.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["pos_local_sql_backup", "pos_custom_cake"],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_local_sql_backup_cake/static/src/app/cake_config_cache.js",
            "pos_local_sql_backup_cake/static/src/app/cake_orders_cache.js",
            "pos_local_sql_backup_cake/static/src/app/local_cake_store.js",
            "pos_local_sql_backup_cake/static/src/app/pos_order_patch.js",
            "pos_local_sql_backup_cake/static/src/app/cake_backup.js",
            "pos_local_sql_backup_cake/static/src/app/cake_offline.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
