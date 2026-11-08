# -*- coding: utf-8 -*-
{
    "name": "PT Inventory As-of Adjustment",
    "version": "19.0.1.0.13",
    "category": "Inventory",
    "summary": "Import counted qty as of a past date, review, and apply in batches",
    "description": """
Upload a CSV of counted quantities as of a specific date (by product_id or sku).
The module computes the correction against historical on-hand, lets you
review lines, then applies inventory adjustments in cron chunks with that
past counting/accounting date.
Products with stock at the default location on that date that were left off
the sheet are added as counted quantity 0.
    """,
    "author": "Peerless Technology",
    "website": "https://www.peerlesstec.com",
    "depends": [
        "stock",
        "stock_account",
    ],
    "data": [
        "security/inventory_as_of_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/inventory_as_of_views.xml",
        "views/menus.xml",
    ],
    "external_dependencies": {
        "python": ["xlsxwriter"],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
