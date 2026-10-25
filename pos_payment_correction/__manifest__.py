{
    "name": "POS Payment Correction",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Correct wrong POS payments on posted orders with audit links and optional journal entry",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizard/pos_payment_correction_wizard_views.xml",
        "views/pos_payment_views.xml",
        "views/pos_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
