{
    "name": "POS Tax Fixed Name",
    "version": "19.0.1.0.0",
    "summary": "Force fixed POS tax names across languages",
    "author": "Anabtawi",
    "category": "Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account"],
    "data": [
        "views/account_tax_views.xml",
        "views/account_tax_group_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_tax_fixed_name/static/src/js/pos_tax_fixed_name_patch.js",
        ],
    },
    "installable": True,
    "application": False,
}
