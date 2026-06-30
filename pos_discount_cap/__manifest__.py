{
    "name": "POS Pricelist Discount Cap",
    "summary": "Apply pricelist discounts with a payment-time cap in POS.",
    "version": "19.0.5.4.0",
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
            "pos_discount_cap/static/src/app/discount_cap_utils.js",
            "pos_discount_cap/static/src/app/discount_cap_payment.js",
            "pos_discount_cap/static/src/app/discount_cap_orderline.js",
            "pos_discount_cap/static/src/app/discount_cap_receipt.js",
            "pos_discount_cap/static/src/app/discount_cap_templates.xml",
        ],
    },
    "installable": True,
    "application": False,
}
