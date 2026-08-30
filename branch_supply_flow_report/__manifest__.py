# -*- coding: utf-8 -*-
{
    "name": "Branch Supply Flow Report",
    "version": "19.0.1.0.4",
    "summary": "Track branch request, dispatch, receipt, returns, and POS sales by product",
    "description": """
Branch supply flow report for a selected period and branch location.

Columns per product:
- Requested quantity (dispatch transfer demand)
- Sent quantity net of returns (factory to intermediate)
- Received quantity net of returns (intermediate to branch stock)
- Returns (dispatch + receipt returns combined)
- Sold quantity (POS sales at the branch)
    """,
    "category": "Inventory/Inventory",
    "author": "Anabtawi Group",
    "depends": ["stock", "point_of_sale"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/branch_supply_flow_wizard_views.xml",
        "views/branch_supply_flow_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
