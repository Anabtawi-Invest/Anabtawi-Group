{
    'name': 'Factory Attendance & Payroll Reconciliation',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Automatic 1h break deduction and monthly Overtime/Undertime netting from Attendances.',
    'author': 'Custom Solutions',
    'license': 'OPL-1',
    'depends': [
        'hr_contract',
        'hr_payroll',
        'hr_attendance',
    ],
    'data': [
        'data/hr_payroll_data.xml',
        'data/test_attendance_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
