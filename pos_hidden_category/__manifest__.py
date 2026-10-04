# -*- coding: utf-8 -*-
{
    "name": "POS Hidden Categories",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Hide POS categories from the POS screen while keeping their products searchable",
    "description": """
POS Hidden Categories
=====================

Adds a "Hide in POS UI" option on POS product categories. Hidden categories
are not shown in the POS category bar, and their products are not shown in
the default product grid. The products are still loaded and appear when the
cashier searches for them (by name, internal reference or barcode).
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_category_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_hidden_category/static/src/app/category_selector_patch.js",
            "pos_hidden_category/static/src/app/pos_store_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
