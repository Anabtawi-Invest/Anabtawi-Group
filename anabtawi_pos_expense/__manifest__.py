{
    "name": "Anabtawi POS Expenses",
    "summary": "Petty-cash expenses from the POS with a revolving limit, receipt photo and approval",
    "version": "19.0.1.3.1",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/pos_expense_type_views.xml",
        "views/pos_expense_views.xml",
        "views/res_config_settings_views.xml",
        "views/pos_expense_upload_templates.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "anabtawi_pos_expense/static/src/app/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
