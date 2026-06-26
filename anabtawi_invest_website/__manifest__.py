# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Invest Corporate Website',
    'version': '1.1',
    'summary': 'Premium corporate portfolio website for Anabtawi Invest with sweets-inspired dark theme',
    'description': """
        Anabtawi Invest Corporate Website.
        Features a luxury dark theme inspired by anabtawisweets.com, with cinematic hero highlights,
        a custom corporate portfolio layout, and smooth public widget animations.
    """,
    'author': 'Antigravity Odoo Developer',
    'category': 'Website',
    'depends': ['website'],
    'data': [
        'views/website_templates.xml',
        'views/snippets.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'anabtawi_invest_website/static/src/scss/website_style.scss',
            'anabtawi_invest_website/static/src/js/website_animation.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
