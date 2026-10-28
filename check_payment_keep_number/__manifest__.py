{
    'name': 'Check Payment Keep Number',
    'version': '19.0.1.0.0',
    'summary': 'Keep the check number when a payment is reset to draft',
    'description': """
Check Payment Keep Number
=========================

Resetting a posted check payment to draft, then posting it again, keeps the
same check number. The check sequence does not advance.

Changing the journal or payment method, or voiding the check, clears that
protection. The next post takes a new number.

Without this module, every post takes the next number from the sequence.
    """,
    'author': 'Agile Consulting',
    'website': 'https://www.agilemena.com',
    'license': 'OPL-1',
    'category': 'Accounting/Payments',
    'depends': ['print_check'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
