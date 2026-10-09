# -*- coding: utf-8 -*-
{
    "name": "Executive Company Cost Dashboard",
    "version": "19.0.2.0.0",
    "category": "Accounting/Reporting",
    "summary": "Chairman's cockpit: group P&L, sister companies, branches and cost intelligence in one screen.",
    "description": """
Executive Company Cost Dashboard
================================
A read-only, real-time executive cockpit built on the posted general ledger:

* Reconciles with Odoo's Profit & Loss (same account types, posted entries only)
* Group KPIs with previous-period comparison, monthly trend and profit waterfall
* Side-by-side sister companies and a cost benchmark between them
* Branch leaderboard (analytic accounts) with rent-to-sales ratio and health status
* Cost intelligence by function: rent, payroll, utilities, IT/telecom, delivery platforms,
  fleet, security, maintenance, waste & shrinkage, government & finance
* Chairman alerts that highlight what needs attention
* Smart Scanner that classifies the chart of accounts (Arabic & English) automatically
""",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["account", "analytic", "web"],
    "data": [
        "security/security_groups.xml",
        "security/ir.model.access.csv",
        "data/default_buckets_data.xml",
        "views/cost_bucket_views.xml",
        "views/analytic_map_views.xml",
        "views/dashboard_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "executive_company_cost_dashboard/static/src/scss/dashboard.scss",
            "executive_company_cost_dashboard/static/src/js/dashboard.js",
            "executive_company_cost_dashboard/static/src/xml/dashboard.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
