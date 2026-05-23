{
    "name": "POS Historical Purge",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Dependency-aware purge of POS data before a cutoff date",
    "depends": [
        "point_of_sale",
        "stock_account",
        "account",
        "mail",
    ],
    "data": [
        "security/pos_historical_purge_security.xml",
        "security/ir.model.access.csv",
        "wizard/pos_purge_wizard_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
