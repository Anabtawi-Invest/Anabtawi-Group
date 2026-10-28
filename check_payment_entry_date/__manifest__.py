{
    'name': 'Check Payment Entry Date',
    'version': '19.0.1.1.0',
    'summary': 'Post check payments with today as the journal entry date',
    'description': """
Check Payment Entry Date
========================

While a check payment is still in draft, its accounting date stays on today.
The printed cheque keeps the separate Check Date from Print Check.

Install this together with Print Check. Without this module, the payment Date
is the journal entry date and Check Date is only the date printed on the cheque.
    """,
    'author': 'Agile Consulting',
    'website': 'https://www.agilemena.com',
    'license': 'OPL-1',
    'category': 'Accounting/Payments',
    'depends': ['print_check'],
    'data': [
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
