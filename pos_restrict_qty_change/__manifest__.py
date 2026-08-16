{
    "name": "POS Restrict Quantity Change",
    "summary": "Restrict POS quantity changes per product and user group",
    "version": "19.0.1.0.4",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "pos_hr",
    ],
    "data": [
        "security/security.xml",
        "views/product_template_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_restrict_qty_change/static/src/app/pos_store.js",
            "pos_restrict_qty_change/static/src/app/product_screen.js",
            "pos_restrict_qty_change/static/src/app/order_summary.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
