{
    "name": "POS Close IP Restrict",
    "summary": "Allow closing a POS session only from configured device IPs.",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_close_ip_restrict/static/src/app/pos_store.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
