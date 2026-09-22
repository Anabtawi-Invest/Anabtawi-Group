# -*- coding: utf-8 -*-
{
    "name": "Stock Period Movement Report",
    "version": "19.0.1.0.5",
    "summary": "Opening, receipts, sales, transfers and closing by location and product",
    "description": """
Stock Period Movement Report under Inventory > Reporting.

For each location and product in a date range:
- Opening balance
- Receipt / Sale / Transfer In / Transfer Out
- Other In / Other Out
- Closing balance

Filter by location and/or product. Export to Excel.
    """,
    "category": "Inventory/Inventory",
    "author": "Anabtawi Group",
    "depends": ["stock"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_period_movement_wizard_views.xml",
        "views/stock_period_movement_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
