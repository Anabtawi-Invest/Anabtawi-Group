{
    "name": "Anabtawi POS Cash In/Out Reasons",
    "summary": "Predefined reasons selection on the POS Cash In/Out popup",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_cash_move_reason_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "anabtawi_pos_cash_move_reason/static/src/app/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
