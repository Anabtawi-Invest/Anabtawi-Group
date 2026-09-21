# -*- coding: utf-8 -*-
{
    "name": "Stock Location Quantity Report",
    "version": "19.0.1.0.3",
    "summary": "Location stock reports: live qty and period movement (opening/closing)",
    "description": """
Stock reporting tools under Inventory > Reporting:

1) Stock Location Quantity Report
   - On Hand + Planned or Done Incoming/Outgoing

2) Stock Period Movement Report
   - Opening balance
   - Receipt / Sale / Transfer In / Transfer Out during the period
   - Closing balance
   - Excel export
    """,
    "category": "Inventory/Inventory",
    "author": "Anabtawi Group",
    "depends": ["stock"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_location_qty_wizard_views.xml",
        "wizard/stock_period_movement_wizard_views.xml",
        "views/stock_location_qty_report_views.xml",
        "views/stock_period_movement_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
