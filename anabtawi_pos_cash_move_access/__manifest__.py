{
    "name": "AAnabtawi POS Cash In/Out Access",
    "summary": "Allow selected POS cashiers to use Cash In/Out",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "pos_hr",
    ],
    "data": [
        "security/security.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "anabtawi_pos_cash_move_access/static/src/app/chrome.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
