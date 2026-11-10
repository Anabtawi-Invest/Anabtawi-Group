{
    'name': 'Payroll Read Only',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Let selected users open payroll and view it without creating or editing anything.',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': [
        'hr_payroll',
    ],
    'data': [
        'security/security.xml',
    ],
    'installable': True,
    'application': False,
}
