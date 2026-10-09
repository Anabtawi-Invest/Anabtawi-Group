# -*- coding: utf-8 -*-
{
    "name": "Executive Company Cost Dashboard",
    "version": "19.0.1.0.0",
    "category": "Accounting/Reporting",
    "summary": "Executive P&L & Departmental Cost Intelligence across Holding, Sister Companies & 21 Branches",
    "description": """
Executive Company Cost Dashboard for Anabtawi Group
===================================================
Key Capabilities:
* Consolidated Anabtawi Invest Group view + Sister companies (United, Alhadaf, Najeed)
* 21 Branches matrix & leaderboard with real-time status indicators (Profitable / Warning / Loss)
* Departmental cost breakdown (IT, HR, Accounting, Branch Operations, Maintenance, CCTV & Civilian Security)
* Specific tracking of Shop Leases/Rent, Utilities (Power/Water), Internet/Telecom, Delivery app commissions
* Auto-Discovery Scanner that maps Chart of Accounts and Analytic dimensions automatically
* Non-invasive, strictly read-only SQL queries with zero server performance impact
""",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "account",
        "analytic",
        "web",
    ],
    "data": [
        "security/security_groups.xml",
        "security/ir.model.access.csv",
        "data/default_buckets_data.xml",
        "views/cost_bucket_config_views.xml",
        "views/ceo_cost_dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "executive_company_cost_dashboard/static/src/scss/ceo_cost_dashboard.scss",
            "executive_company_cost_dashboard/static/src/js/ceo_cost_dashboard.js",
            "executive_company_cost_dashboard/static/src/xml/ceo_cost_dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
