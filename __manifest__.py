# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sweets Corporate Website',
    'version': '1.0',
    'summary': 'Premium custom website module for Anabtawi Sweets with Arabic RTL support and cinematic scroll animation',
    'description': """
        Anabtawi Sweets Corporate Website.
        Features an authentic Arabic sweets brand theme with scroll-driven video scrubbing,
        floating social sidebar, premium product catalog, and full Odoo website integration.
    """,
    'author': 'Antigravity / Anabtawi Sweets',
    'category': 'Website',
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
            'theme_anabtawi_sweets/static/src/scss/website_style.scss',
            'theme_anabtawi_sweets/static/src/js/website_animation.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
