{
    "name": "Inventory Delivery Transaction Report",
    "summary": "Wizard report for POS transactions by date and location",
    "version": "19.0.1.0.0",
    "category": "Inventory/Reporting",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "point_of_sale",
    ],
    "data": [
        "views/delivery_transaction_report_wizard_views.xml",
        "report/delivery_transaction_report_templates.xml",
        "report/delivery_transaction_report_action.xml",
    ],
    "installable": True,
    "application": False,
}
