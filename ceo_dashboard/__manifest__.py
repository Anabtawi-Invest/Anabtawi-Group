# -*- coding: utf-8 -*-
{
    'name': 'Executive CEO Dashboard | Finance, Sales, CRM, Inventory, HR & Projects KPIs',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Dashboards',
    'summary': 'One-screen executive dashboard: Revenue, Profit, Cash, AR/AP, Sales & CRM Pipeline, '
               'Inventory, HR and Project KPIs with daily/weekly/monthly/yearly & custom date filters.',
    'description': "",
    'author': 'MOHAMMAD NABIL',
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
