{
    'name': 'Print Bank Cheque - Jordan & Arab Countries',
    'version': '19.0.2.8.0',
    'description': """
Print Bank Cheque Module
========================

A comprehensive cheque printing solution for Odoo 19 with support for:
- Jordanian and Arab country currencies (21+ currencies)
- Arabic Tafqeet (number to words conversion)
- Real-time cheque preview
- Customizable text positioning
- RTL-safe layout (works in Arabic UI)
- Glassmorphism modern UI
- LocalStorage persistence for settings

Features:
---------
* Preview cheque before printing
* Adjust font size, weight, and position of all fields
* Arabic honorific shortcuts (السيد، السادة، etc.)
* Multiple currencies with proper fraction names
* Thousands separator options
* Arabic/English numeral styles
* Crossing text with orientation options
    """,
    'summary': 'Print Bank Cheque with Arabic Tafqeet - Jordan & Arab Countries',
    'author': 'Agile Consulting',
    'website': 'https://www.agilemena.com',
    'license': 'OPL-1',
    'category': 'Accounting/Payments',
    'depends': ['base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/print_check_views.xml',
        'views/payment_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # CSS must load first for RTL isolation
            'print_check/static/src/css/print_check.css',
            # Tafqeet library (number to words)
            'print_check/static/src/js/tafqeet.js',
            # Main application controller
            'print_check/static/src/js/print_check.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}
