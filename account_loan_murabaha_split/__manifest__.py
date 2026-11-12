{
    'name': 'Loan Murabaha Split',
    'version': '19.0.1.6.0',
    'category': 'Accounting/Accounting',
    'summary': 'Split loan principal and murabaha interest into separate journal entries',
    'description': """
When enabled on a loan, Confirm creates:
- Payment entry at full installment amount: Dr Long Term / Cr Short Term (principal + interest)
- Separate murabaha entry: Dr Expense / Cr selected short-term liability (interest)
- LT-ST reclassification/reversal using payment (principal + interest) for the next 12 lines

Installment dating:
- Principal & Interest (and Murabaha when split) use the loan-line date
- LT-ST reclassification stays on month-end; reversal on the next day

Optional analytic account on the loan is applied at 100% on journal items
that use the Expense Account only (checkbox on or off).

Optional Label (البيان) field under Asset Group:
- Checkbox off: label on all 3 lines of the Principal & Interest entry
- Checkbox on: label on Murabaha entry (2 lines) and Principal & Interest entry (2 lines)
Label format: "{label} {entry accounting date}"
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
