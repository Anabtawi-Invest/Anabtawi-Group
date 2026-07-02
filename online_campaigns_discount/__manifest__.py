{
    "name": "Online Campaigns Discount",
    "version": "19.0.2.0.1",
    "category": "Sales/Point of Sale",
    "summary": "Approved aggregator campaigns with POS, calendar, accounting, and reporting",
    "author": "Anabtawi Sweets",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/online_campaign_views.xml",
        "views/pos_order_views.xml",
        "views/online_campaign_reporting_views.xml",
        "views/online_campaign_settlement_views.xml",
        "views/menu.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "online_campaigns_discount/static/src/js/online_campaign_loader.js",
            "online_campaigns_discount/static/src/js/online_discount_logic.js",
            "online_campaigns_discount/static/src/js/receipt_extension.js",
            "online_campaigns_discount/static/src/xml/receipt_extension.xml",
            "online_campaigns_discount/static/src/scss/online_campaign_receipt.scss",
        ],
    },
    "installable": True,
    "application": True,
}
