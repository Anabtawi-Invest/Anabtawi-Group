# -*- coding: utf-8 -*-
{
    'name': 'CEO Main Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Dashboards',
    'summary': 'Executive dashboard: daily purchases and purchase price increase / decrease tracking.',
    'author': 'ANABTAWI',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'purchase',
    ],
    'data': [
        'security/security.xml',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ceo_main_dashboard/static/src/scss/dashboard.scss',
            'ceo_main_dashboard/static/src/js/dashboard.js',
            'ceo_main_dashboard/static/src/xml/dashboard.xml',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}
