{
    "name": "POS Open Amount Discount",
    "summary": "Apply a fixed open amount reduction as sequential line discounts in POS.",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_open_amount_discount/static/src/app/open_amount/open_amount_utils.js",
            "pos_open_amount_discount/static/src/app/open_amount/control_buttons_open_amount.js",
            "pos_open_amount_discount/static/src/app/open_amount/control_buttons_open_amount.xml",
        ],
    },
    "installable": True,
    "application": False,
}
