{
    'name': 'Bank Journal Draft Restriction',
    'version': '19.0.1.0.0',
    'summary': 'Only selected users can reset bank journal entries to draft',
    'description': """
Bank Journal Draft Restriction
==============================

Reset to Draft on a bank journal is limited to users in the group
"Bank Journal / Reset to Draft".

Customer invoices, vendor bills, and cash journals are unchanged.
    """,
    'author': 'Agile Consulting',
    'website': 'https://www.agilemena.com',
    'license': 'OPL-1',
    'category': 'Accounting/Accounting',
    'depends': ['account'],
    'data': [
        'security/security.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
