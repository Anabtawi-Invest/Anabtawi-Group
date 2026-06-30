{
    "name": "POS Pricelist Discount Cap",
    "summary": "Apply pricelist discounts with a payment-time cap in POS.",
    "version": "19.0.3.0.0",
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
            "pos_discount_cap/static/src/app/models/pos_order_cap_discount.js",
            "pos_discount_cap/static/src/app/discount_cap_payment.js",
            "pos_discount_cap/static/src/app/orderline_cap_discount.xml",
            "pos_discount_cap/static/src/app/orderline_cap_discount.js",
            "pos_discount_cap/static/src/app/order_receipt_cap_discount.xml",
            "pos_discount_cap/static/src/app/order_receipt_cap_discount.js",
        ],
    },
    "installable": True,
    "application": False,
}
