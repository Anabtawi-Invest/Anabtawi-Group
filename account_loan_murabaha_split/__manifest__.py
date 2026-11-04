{
    'name': 'Loan Murabaha Split',
    'version': '19.0.1.2.0',
    'category': 'Accounting/Accounting',
    'summary': 'Split loan principal and murabaha interest into separate journal entries',
    'description': """
When enabled on a loan, Confirm creates:
- Payment entry at full installment amount: Dr Long Term / Cr Short Term (principal + interest)
- Separate murabaha entry: Dr Expense / Cr selected short-term liability (interest)
- LT-ST reclassification/reversal using payment (principal + interest) for the next 12 lines

Optional analytic account on the loan is applied at 100%:
- Checkbox off: expense line only
- Checkbox on: both murabaha expense and murabaha liability lines
    """,
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': ['account_loans', 'analytic'],
    'data': [
        'views/account_loan_views.xml',
    ],
    'installable': True,
    'application': False,
}
