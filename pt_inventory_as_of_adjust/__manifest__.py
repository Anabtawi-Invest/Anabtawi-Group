# -*- coding: utf-8 -*-
{
    "name": "PT Inventory As-of Adjustment",
    "version": "19.0.1.0.0",
    "category": "Inventory",
    "summary": "Import counted qty as of a past date, review, and apply in batches",
    "description": """
Upload a CSV of counted quantities as of a specific date.
The module computes the correction against historical on-hand, lets you
review lines, then applies inventory adjustments in cron chunks with that
past counting/accounting date.
    """,
    "author": "Peerless Technology",
    "website": "https://www.peerlesstec.com",
    "depends": [
        "stock",
        "stock_account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/inventory_as_of_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
