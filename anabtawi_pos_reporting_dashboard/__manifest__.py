# -*- coding: utf-8 -*-
{
    "name": "Unified POS Reporting & Branch Dashboard",
    "version": "19.0.1.0.2",
    "category": "Point of Sale",
    "summary": "Comprehensive POS reporting and executive dashboard for Cash/Visa sales, Cash In/Out, Pledges, Advance Orders per branch",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "account",
        "web",
        "pos_advance_order",
        "pos_ameen_daily_operation",
    ],
    "data": [
        "security/security_groups.xml",
        "security/ir.model.access.csv",
        "wizard/pos_unified_report_wizard_views.xml",
        "views/pos_dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "anabtawi_pos_reporting_dashboard/static/src/scss/pos_dashboard.scss",
            "anabtawi_pos_reporting_dashboard/static/src/js/pos_dashboard.js",
            "anabtawi_pos_reporting_dashboard/static/src/xml/pos_dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
