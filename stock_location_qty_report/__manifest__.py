# -*- coding: utf-8 -*-
{
    "name": "Stock Location Quantity Report",
    "version": "19.0.1.0.2",
    "summary": "On hand plus planned or done incoming/outgoing by location and product",
    "description": """
Stock location quantity report.

For each location and product:
- On Hand (current stock)
- Incoming / Outgoing: choose Planned (not done) or Done
- Forecast (On Hand + Incoming - Outgoing for Planned mode)

In Done mode, optional date range filters validated moves (activity).
Those done quantities are already included in On Hand.

Filter by location and/or product. Export to Excel.
    """,
    "category": "Inventory/Inventory",
    "author": "Anabtawi Group",
    "depends": ["stock"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_location_qty_wizard_views.xml",
        "views/stock_location_qty_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
