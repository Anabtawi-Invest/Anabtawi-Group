{
    "name": "In Point of Sale , Fiscal Position Keep Pricelist Price",
    "summary": "Keep sale pricelist unit price unchanged with selected fiscal positions.",
    "version": "19.0.1.2.0",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "author": "Anabtawi",
    "depends": ["sale_management", "account", "point_of_sale"],
    "data": [
        "views/account_fiscal_position_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "sale_fiscal_position_keep_price/static/src/pos/fiscal_position_keep_price_patch.js",
        ],
    },
    "installable": True,
    "application": False,
}
