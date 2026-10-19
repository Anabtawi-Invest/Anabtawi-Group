{
    "name": "POS Exclusive Payment Method",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Prevent mixing exclusive payment methods in POS orders",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_exclusive_payment_method/static/src/app/screens/payment_screen/payment_screen.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
