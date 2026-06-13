{
    "name": "POS Delivery Amount",
    "summary": "Capture and post POS delivery amount at closing",
    "version": "19.0.2.0.0",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
        "views/pos_session_views.xml",
        "views/pos_delivery_report_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_delivery_amount/static/src/app/components/delivery_amount_popup/delivery_amount_popup.js",
            "pos_delivery_amount/static/src/app/components/delivery_amount_popup/delivery_amount_popup.xml",
            "pos_delivery_amount/static/src/app/patches/close_pos_popup_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
