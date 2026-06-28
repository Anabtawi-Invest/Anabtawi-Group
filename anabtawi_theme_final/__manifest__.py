# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sweets Theme',
    'version': '1.0',
    'summary': 'Custom website theme replicating anabtawisweets.com',
    'description': """
        Anabtawi Sweets Custom Theme.
        This theme applies the design, layout, and colors from the original 
        anabtawisweets.com to Odoo's website application.
    """,
    'author': 'Antigravity Odoo Developer',
    'category': 'Theme/Corporate',
    'depends': ['website'],
    'data': [
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'anabtawi_theme_final/static/src/scss/website_style.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
