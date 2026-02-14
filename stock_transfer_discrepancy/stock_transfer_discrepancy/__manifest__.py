{
    "name": "Stock Transfer Discrepancy",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Require reason when validated quantities are lower than expected",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "reports/stock_transfer_discrepancy_report.xml",
        "views/stock_location_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_transfer_discrepancy_views.xml",
        "wizard/stock_transfer_discrepancy_wizard_views.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}

