{
    'name': 'Check Payment Entry Date',
    'version': '19.0.1.7.0',
    'summary': 'Post check payments with today as the journal entry date',
    'description': """
Check Payment Entry Date
========================

Tick Check on a journal payment method (Incoming or Outgoing Payments).
Confirming a payment that uses a ticked method sets the journal entry date to today.
While that payment is still in draft, its accounting date stays on today.
The printed cheque keeps the separate Check Date from Print Check.

Weekdays ticked under Invoicing settings, Vendor Payments, cannot be used as
the Check Date. Saving or posting such a payment raises an error.

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
        'views/account_journal_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
