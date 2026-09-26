# -*- coding: utf-8 -*-
{
    'name': 'Executive CEO Dashboard | Finance, Sales, CRM, Inventory, HR & Projects KPIs',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Dashboards',
    'summary': 'One-screen executive dashboard: Revenue, Profit, Cash, AR/AP, Sales & CRM Pipeline, '
               'Inventory, HR and Project KPIs with daily/weekly/monthly/yearly & custom date filters.',
    'description': """
Executive / CEO Dashboard
==========================
A single, beautiful, real-time dashboard for business owners and executives.

Finance & Accounting
---------------------
* Total Revenue & Total Expenses (Today / Month / Year) vs same period last year
* Gross Profit & Gross Margin %, Net Profit
* Cash Position (bank + cash balance)
* Accounts Receivable / Accounts Payable
* Overdue Invoices (count & amount, highlighted)
* DSO (Days Sales Outstanding)
* Top 5 overdue customers

Sales & CRM
------------
* Sales Orders confirmed (today / week / month)
* Revenue vs Monthly Target gauge
* Pipeline Value & Win Rate, Average Deal Size
* Top 5 customers by revenue, New leads this week, Opportunities closing this month

Inventory
----------
* Total Inventory Value, Low Stock Alerts
* Pending Deliveries / Receipts due today, Overdue Purchase Orders, Stock Turnover Rate

HR
---
* Active Employees, Pending Leave Requests, On Leave Today
* Open Job Positions, Late Clock-ins Today

Projects & Helpdesk
---------------------
* Overdue Tasks, Tasks Due Today, Projects Over Budget
* Billable Hours vs Target, Open Helpdesk Tickets

Includes global Date From / Date To filter with quick presets (Today, This Week,
This Month, This Year, Custom) applied across the whole dashboard.
    """,
    'author': 'Solomon Yeshiwas',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base', 'web',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web/static/lib/Chart/Chart.js',
            'ceo_dashboard/static/src/scss/dashboard.scss',
            'ceo_dashboard/static/src/js/dashboard.js',
            'ceo_dashboard/static/src/xml/dashboard.xml',
        ],
    },
    'images': [
        'static/description/banner.png',
        'static/description/dashboard_main.png',
        'static/description/finance_tab.png',
        'static/description/sales_tab.png',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
