{
    "name": "POS Close IP Restrict",
    "summary": "Allow closing a POS session only from registered devices and optional IPs.",
    "version": "19.0.1.1.1",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_close_ip_restrict/static/src/app/close_device_token.js",
            "pos_close_ip_restrict/static/src/app/pos_store.js",
            "pos_close_ip_restrict/static/src/app/closing_popup.js",
            "pos_close_ip_restrict/static/src/app/navbar.js",
            "pos_close_ip_restrict/static/src/app/navbar.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
