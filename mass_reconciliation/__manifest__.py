{
    'name': 'كمتلة Mass Reconciliation (Lateness Coverage)',
    'version': '19.0.1.0.1-fix-leaveguard-fix-leave-actions',
    'summary': 'Cover lateness using OT buckets then Annual Leave (hours) then remaining lateness for payroll deduction. No OT Bank.',
    'category': 'Human Resources/Payroll',
    'author': 'Softobia',
    'license': 'LGPL-3',
    'depends': ['hr_payroll', 'hr_holidays'],
    'data': [
        'data/payslip_input_type.xml',
        'security/ir.model.access.csv',
        'views/hr_payslip_views.xml',
        'data/server_actions.xml',
    ],
    'installable': True,
    'application': False,
}
