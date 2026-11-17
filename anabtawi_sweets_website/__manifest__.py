# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sweets Website Theme',
    'version': '19.0.1.0.2',
    'summary': 'Premium website theme for Anabtawi Sweets with Arabic RTL support',
    'description': """
        Anabtawi Sweets corporate website theme for Odoo 19.
        Features a custom homepage, jobs page, and contact form integrated with the standard Odoo website builder.
    """,
    'author': 'Anabtawi Sweets',
    'category': 'Website',
    'images': [
        'static/description/icon.png',
    ],
    'depends': ['website', 'website_sale', 'website_hr_recruitment'],
    'data': [
        'views/layout.xml',
        'views/snippets/snippets.xml',
        'views/home.xml',
        'views/shop_templates.xml',
        'views/jobs.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'anabtawi_sweets_website/static/src/scss/primary_variables.scss',
        ],
        'web.assets_frontend': [
            'anabtawi_sweets_website/static/src/scss/website_style.scss',
            'anabtawi_sweets_website/static/src/js/shop_custom.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
