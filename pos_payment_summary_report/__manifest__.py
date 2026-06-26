{
    'name': 'POS Payment Summary Report',
    'version': '1.0',
    'author': 'Anabtawi',
    'category': 'Point of Sale',
    'summary': 'Payment summary report grouped by POS session and payment method',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'report/pos_payment_summary_report.xml',
        'wizard/pos_payment_summary_wizard_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
