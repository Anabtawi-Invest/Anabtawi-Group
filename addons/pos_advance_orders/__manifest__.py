{
    "name": "POS Advance Orders + Pledge",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Advance Orders, Pledge Deposits, Accounting Liability",
    "depends": [
        "point_of_sale", 
        "account", 
        "contacts", 
        "product"
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
        "views/advance_order_views.xml",
        "views/discount_profile_views.xml",

    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_advance_orders/static/src/pos/index.js",
            "pos_advance_orders/static/src/pos/**/*.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
