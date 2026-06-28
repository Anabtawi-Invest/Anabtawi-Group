# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sweets Theme',
    'description': 'A premium custom website module for Anabtawi Sweets with Arabic RTL support and cinematic scroll animation.',
    'category': 'Website',
    'version': '19.0.1.0.0',
    'author': 'Antigravity / Anabtawi Sweets',
    'depends': ['website'],
    'data': [
        'views/layout_templates.xml',
        'views/homepage_templates.xml',
        'views/about_templates.xml',
        'views/branches_templates.xml',
        'views/catalog_templates.xml',
        'views/contact_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'theme_anabtawi_sweets/static/src/css/theme.css',
            'theme_anabtawi_sweets/static/src/js/theme.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
