# -*- coding: utf-8 -*-
{
    "name": "Branch Supply Flow Dashboard",
    "version": "19.0.1.0.0",
    "summary": "Persistent snapshots and dashboard charts for branch supply flow analysis",
    "description": """
Branch Supply Flow Dashboard
============================

Stores periodic snapshots of the Branch Supply Flow Report and provides
dashboard views with KPIs, charts, and alert filters for:

- Fill rate (requested vs received)
- Transit loss (sent vs received)
- Sell-through (received vs sold)
- Unsold stock at branches
    """,
    "category": "Inventory/Inventory",
    "author": "Anabtawi Group",
    "depends": ["branch_supply_flow_report"],
    "data": [
        "security/ir.model.access.csv",
        "data/branch_supply_flow_snapshot_cron.xml",
        "wizard/branch_supply_flow_snapshot_wizard_views.xml",
        "views/branch_supply_flow_snapshot_line_views.xml",
        "views/branch_supply_flow_snapshot_views.xml",
        "views/branch_supply_flow_dashboard_menus.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
