{
    "name": "POS Set Default Customer",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Server action to fill empty POS customers",
    "author": "Anabtawi",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/confirm_set_default_customer_wizard_views.xml",
        "data/server_action.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
