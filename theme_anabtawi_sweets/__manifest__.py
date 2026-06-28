# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sweets Website Theme',
    'version': '19.0.1.0.0',
    'summary': 'Premium website theme for Anabtawi Sweets with Arabic RTL support',
    'description': """
        Anabtawi Sweets corporate website theme for Odoo 19.
        Features a custom homepage, product catalog, branches, about page,
        and contact form integrated with the standard Odoo website builder.
    """,
    'author': 'Anabtawi Sweets',
    'category': 'Theme',
    'depends': ['website'],
    'data': [
        'views/layout.xml',
        'views/snippets/snippets.xml',
        'views/home.xml',
        'data/pages/about.xml',
        'data/pages/branches.xml',
        'data/pages/catalog.xml',
        'views/contact.xml',
        'data/menus.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'theme_anabtawi_sweets/static/src/scss/primary_variables.scss',
        ],
        'web.assets_frontend': [
            'theme_anabtawi_sweets/static/src/scss/website_style.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
