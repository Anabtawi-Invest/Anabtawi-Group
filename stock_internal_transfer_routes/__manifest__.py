# -*- coding: utf-8 -*-
{
    "name": "Stock Internal Transfer Routes",
    "version": "19.0.1.0.0",
    "summary": "Apply product pull routes when confirming internal transfers",
    "description": """
When confirming an internal transfer, apply matching pull rules on the moves
(via _adjust_procure_method) so Supply Method "Trigger Another Rule" creates
the upstream replenishment transfer automatically.
    """,
    "category": "Inventory/Inventory",
    "author": "Anabtawi Group",
    "depends": ["stock"],
    "data": [
        "views/stock_picking_type_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
