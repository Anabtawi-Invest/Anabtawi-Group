# -*- coding: utf-8 -*-
{
    "name": "Location Quantity on Hand",
    "version": "19.0.1.0.0",
    "summary": "Export quantity on hand by location and product for one date",
    "description": """
Wizard under Inventory > Reporting.

Choose one date, all internal locations or one location, and all products
or specific products. Download an Excel file with the location, the product,
and the quantity on hand at the end of that date.

The quantity uses the same sources as Inventory at Date:
stock.quant for the quantity now, and done stock.move records after that
datetime.
    """,
    "category": "Inventory/Inventory",
    "author": "Anabtawi Group",
    "depends": ["stock"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_location_qty_on_date_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
