{
    'name': 'Factory Attendance & Payroll Reconciliation',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Automatic 1h break deduction, planning shift integration, and 3-Tier Waterfall Net Undertime Settlement.',
    'author': 'Custom Solutions',
    'license': 'OPL-1',
    'depends': [
        'hr_payroll',
        'hr_attendance',
    ],
    'data': [
        'data/hr_payroll_data.xml',
        'views/hr_payslip_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
