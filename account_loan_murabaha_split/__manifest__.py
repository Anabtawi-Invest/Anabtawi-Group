{
    'name': 'Loan Murabaha Split',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Split loan principal and murabaha interest into separate journal entries',
    'description': """
When enabled on a loan, Confirm creates:
- Principal entry: Dr Long Term / Cr Short Term (principal only)
- Murabaha entry: Dr Expense / Cr selected short-term liability (interest)
    """,
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': ['account_loans'],
    'data': [
        'views/account_loan_views.xml',
    ],
    'installable': True,
    'application': False,
}
