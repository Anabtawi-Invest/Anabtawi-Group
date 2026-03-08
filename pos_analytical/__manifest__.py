# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.

{
    "name": "POS Analytic Account-anabtawi",
    "author": "Softhealer Technologies",
    "website": "https://www.softhealer.com",
    "support": "support@softhealer.com",
    "category": "Point Of Sale",
    "summary": "Link Analytic Account Configure Analytic Account Set Analytic Tags Analytic Journal Items, Analytic Journal Entries Point Of Sale Analytic Account Point Of Sale Analytic Tags POS Analytic Tags POS Analytic Account Analytic Account in POS POS Accounting Analysis POS Journal Analytic POS Configuration Analytic Account Odoo",
    "description": """This module helps configure the 'Analytic Account' in POS orders. You can set the analytic account based on each POS configuration. It automatically applies the 'Analytic Account' to journal entries and journal items, allowing you to analyze POS orders using analytic reports.""",
    "version": "0.0.1",
    "license": "OPL-1",
    "depends": ["point_of_sale", "analytic"],
    "application": True,
    "data": [
        'views/pos_order_views.xml',
        'views/pos_payment_views.xml',
        'views/pos_session_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'sh_pos_analytic_tags/static/src/overrides/models.js'
        ]
    },
    "images": ["static/description/background.png", ],
    "auto_install": False,
    "installable": True,
    "price": 17,
    "currency": "EUR"
}
