{
    "name": "Stock Delivery Transactions Report",
    "summary": "Inventory reporting wizard for delivery transactions",
    "version": "19.0.1.0.0",
    "category": "Inventory/Reporting",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "point_of_sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/delivery_txn_report_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
