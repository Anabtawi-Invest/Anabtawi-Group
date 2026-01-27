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
        "views/discount_profile_views.xml"
    ],
   "assets": {
    "point_of_sale._assets_pos": [
        # JS Entry Point
        "pos_advance_orders/static/src/pos/index.js",

        # XML Templates
        "pos_advance_orders/static/src/pos/**/*.xml",

        # All JS files used in POS
        "pos_advance_orders/static/src/pos/advance_orders_popup.js",
        "pos_advance_orders/static/src/pos/advance_orders_button.js",
        "pos_advance_orders/static/src/pos/pledge_autoline.js",
        "pos_advance_orders/static/src/pos/receipt_split.js",
        "pos_advance_orders/static/src/pos/discount_popup.js",
        "pos_advance_orders/static/src/pos/discount_button.js",
        "pos_advance_orders/static/src/pos/gift_button.js",

        # OPTIONAL — if used on POS frontend (else remove it)
        "pos_advance_orders/static/src/pos/export_flags.js",
    ],
}

    "installable": True,
    "application": False,
    "license": "LGPL-3"
}
