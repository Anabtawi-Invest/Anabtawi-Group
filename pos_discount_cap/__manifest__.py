{
    "name": "POS Pricelist Discount Cap",
    "summary": "Apply pricelist discounts with a payment-time cap in POS.",
    "version": "19.0.4.0.0",
    "category": "Point of Sale",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/product_pricelist_views.xml",
        "views/pos_config_fee_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_discount_cap/static/src/app/discount_cap_payment.js",
        ],
    },
    "installable": True,
    "application": False,
}
