# -*- coding: utf-8 -*-
{
    "name": "Online & Delivery Sales Analytics Dashboard",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Dedicated dashboard for online, e-commerce, and delivery platform sales (Talabat, Careem, Website, etc.) with complete multi-channel breakdown.",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "account",
        "web",
        "pos_advance_order",
        "online_campaigns_discount",
    ],
    "data": [
        "security/security_groups.xml",
        "security/ir.model.access.csv",
        "views/online_sales_channel_views.xml",
        "wizard/online_sales_report_wizard_views.xml",
        "views/online_sales_dashboard_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "anabtawi_online_sales_dashboard/static/src/scss/online_sales_dashboard.scss",
            "anabtawi_online_sales_dashboard/static/src/js/online_sales_dashboard.js",
            "anabtawi_online_sales_dashboard/static/src/xml/online_sales_dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
